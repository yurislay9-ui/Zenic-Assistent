"""
Admin / public endpoints — health, models, projects, system status, audit events.

Includes:
- Public endpoints: /, /health, /ready, /metrics, /v1/models
- Project runner: /v1/project/run, /stop, /running
- Legacy GET endpoints: /v1/projects, /v1/automations, etc.
- Audit events: /v1/audit/events

Auth and tenant endpoints are in _routes_auth.py.
"""

from typing import Any, Dict, Optional

from src.server.fastapi_parts._imports import (
    time,
    logging,
    logger,
    AuthContext,
    ZENIC_VERSION,
    ZENIC_FULL_NAME,
    _HEALTH_AVAILABLE,
    _METRICS_AVAILABLE,
    _AUDIT_AVAILABLE,
    AuditEventType,
)


def register_admin_routes(
    app: Any,
    *,
    orchestrator: Any,
    auth_service: Optional[Any],
    rate_limiter: Optional[Any],
    governor: Optional[Any],
    platform_tag: str,
    start_time: float,
    require_auth_dep: Any,
) -> None:
    """Register public, project, and admin endpoints on *app*."""

    from fastapi import Request, HTTPException, Depends
    from fastapi.responses import JSONResponse, Response

    # ════════════════════════════════════════════════════════
    #  PUBLIC ENDPOINTS (no auth required)
    # ════════════════════════════════════════════════════════

    @app.get("/")
    async def root():
        """Server info and available endpoints."""
        from src.core.shared.contracts import HAS_Z3
        solver = "Z3" if HAS_Z3 else "AC-3"
        version_suffix = f"-{platform_tag}" if platform_tag else ""
        return {
            "status": "active",
            "model": "zenic-agents",
            "version": f"{ZENIC_VERSION}{version_suffix}",
            "server": "FastAPI",
            "auth_enabled": auth_service is not None,
            "endpoints": [
                "/v1/chat/completions", "/v1/models", "/health", "/ready", "/metrics",
                "/v1/generate/app", "/v1/generate/automation", "/v1/generate/niche",
                "/v1/design/schema", "/v1/think", "/v1/reason",
                "/v1/chain/validate", "/v1/chain/execute",
                "/v1/auth/register", "/v1/auth/login", "/v1/auth/refresh",
                "/v1/auth/me", "/v1/auth/api-keys",
                "/v1/tenants", "/v1/tenants/{tenant_id}",
                "/v1/cluster/nodes", "/v1/cluster/status",
                "/v1/tasks/enqueue", "/v1/tasks/{task_id}/status",
                "/v1/saga/start", "/v1/saga/{saga_id}",
                "/v1/actions/dispatch", "/v1/actions/confirm/{action_id}",
                "/v1/actions/approve/{action_id}", "/v1/actions/pending",
                "/v1/executors", "/v1/audit",
                "/docs",
            ],
            "solver": solver,
            "pipeline_levels": 8,
        }

    @app.get("/health")
    async def health():
        """Liveness health check."""
        health_agg = getattr(app.state, "health_aggregator", None)
        if health_agg is not None and _HEALTH_AVAILABLE:
            result = await health_agg.check_liveness()
            status_code = 200 if result.get("status") != "unhealthy" else 503
            return JSONResponse(content=result, status_code=status_code)
        from src.core.shared.contracts import HAS_Z3
        health_data: Dict[str, Any] = {
            "status": "healthy",
            "solver": "Z3" if HAS_Z3 else "AC-3",
            "has_z3": HAS_Z3,
            "mode": "fastapi",
            "uptime_s": int(time.time() - start_time),
        }
        if governor:
            health_data["resources"] = governor.get_status()
            if governor.is_ram_critical():
                health_data["status"] = "degraded"
        return health_data

    @app.get("/ready")
    async def readiness():
        """Readiness probe."""
        health_agg = getattr(app.state, "health_aggregator", None)
        if health_agg is not None and _HEALTH_AVAILABLE:
            result = await health_agg.check_readiness()
            status_code = 200 if result.get("ready") else 503
            return JSONResponse(content=result, status_code=status_code)
        checks: Dict[str, Any] = {}
        try:
            checks["orchestrator"] = orchestrator is not None
        except Exception:
            checks["orchestrator"] = False
        if auth_service:
            try:
                auth_service.get_stats()
                checks["auth_db"] = True
            except Exception:
                checks["auth_db"] = False
        else:
            checks["auth_db"] = None
        ready = all(v is not False for v in checks.values())
        return {"ready": ready, "checks": checks}

    @app.get("/metrics")
    async def metrics():
        """Prometheus-compatible metrics."""
        mc = getattr(app.state, "metrics_collector", None)
        if mc is not None and _METRICS_AVAILABLE:
            if governor:
                try:
                    res = governor.get_status()
                    mc.update_resources(res.get("ram_usage_mb", 0), res.get("cpu_usage_pct", 0))
                except Exception:
                    pass
            mc.update_uptime(time.time() - start_time)
            return Response(content=mc.generate_text_metrics(), media_type="text/plain")
        uptime = int(time.time() - start_time)
        lines = [
            "# HELP zenic_uptime_seconds Server uptime in seconds",
            "# TYPE zenic_uptime_seconds gauge",
            f"zenic_uptime_seconds {uptime}",
            "# HELP zenic_requests_total Total requests served",
            "# TYPE zenic_requests_total counter",
            f"zenic_requests_total {app.state.request_count}",
        ]
        if rate_limiter:
            stats = rate_limiter.get_stats()
            lines.extend([
                "# HELP zenic_rate_limit_accepted Total accepted requests",
                "# TYPE zenic_rate_limit_accepted counter",
                f"zenic_rate_limit_accepted {stats.get('total_accepted', 0)}",
                "# HELP zenic_rate_limit_rejected Total rejected requests",
                "# TYPE zenic_rate_limit_rejected counter",
                f"zenic_rate_limit_rejected {stats.get('total_rejected', 0)}",
            ])
        if governor:
            res = governor.get_status()
            lines.extend([
                f"zenic_ram_usage_mb {res.get('ram_usage_mb', 0):.1f}",
                f"zenic_cpu_usage_pct {res.get('cpu_usage_pct', 0):.1f}",
            ])
        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    @app.get("/v1/models")
    async def list_models():
        """OpenAI-compatible models endpoint."""
        return {
            "object": "list",
            "data": [{"id": "zenic-agents", "object": "model",
                       "created": int(time.time()), "owned_by": "zenic-local"}],
        }

    # ════════════════════════════════════════════════════════
    #  PROJECT RUNNER ENDPOINTS (M6)
    # ════════════════════════════════════════════════════════

    @app.post("/v1/project/run")
    async def run_project(request: Request):
        """Run a generated project with auto venv + deps + server start."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        project_name = body.get("project_name", "")
        if not project_name:
            raise HTTPException(status_code=400, detail="Missing 'project_name' field")
        try:
            from src.core.project_runner import ProjectRunner
            runner = ProjectRunner()
            result = runner.run_project(
                project_name=project_name, port=body.get("port", 0),
                auto_install=body.get("auto_install", True),
                auto_start=body.get("auto_start", True),
            )
            return {
                "success": result.success, "project_name": result.project_name,
                "project_dir": result.project_dir, "port": result.port,
                "pid": result.pid, "health_ok": result.health_ok,
                "installed_deps": result.installed_deps, "failed_deps": result.failed_deps,
                "errors": result.errors, "warnings": result.warnings,
                "startup_time_s": result.startup_time_s,
            }
        except Exception as e:
            logger.error("Project run error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/project/stop")
    async def stop_project(request: Request):
        """Stop a running project."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        project_name = body.get("project_name", "")
        if not project_name:
            raise HTTPException(status_code=400, detail="Missing 'project_name' field")
        try:
            from src.core.project_runner import ProjectRunner
            runner = ProjectRunner()
            stopped = runner.stop_project(project_name)
            return {"success": stopped, "project_name": project_name}
        except Exception as e:
            logger.error("Project stop error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/project/running")
    async def list_running_projects():
        """List all running projects."""
        try:
            from src.core.project_runner import ProjectRunner
            runner = ProjectRunner()
            return {"projects": runner.list_running()}
        except Exception as e:
            logger.error("List running error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ════════════════════════════════════════════════════════
    #  LEGACY GET ENDPOINTS
    # ════════════════════════════════════════════════════════

    @app.get("/v1/projects")
    async def list_projects(status: str = ""):
        try:
            projects = await orchestrator.list_projects(status)
            return {"projects": projects, "total": len(projects)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/automations")
    async def list_automations():
        try:
            automations = await orchestrator.list_automations()
            return {"automations": automations, "total": len(automations)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/niches")
    async def list_niches(domain: str = ""):
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            niches = engine.list_niches(domain)
            result = []
            for name in niches:
                plan = engine.get_niche_plan(name)
                if plan:
                    result.append({"name": name, "entities": len(plan.entities), "blocks": plan.blocks})
            return {"niches": result, "total": len(result), "domain": domain or "all"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/niches/domains")
    async def list_domains():
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            domains = engine.list_domains()
            result = [{"domain": d, "niche_count": len(engine.list_niches(d)),
                       "niches": engine.list_niches(d)} for d in domains]
            return {"domains": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/templates")
    async def list_templates():
        try:
            from src.core.app_generator import AppGenerator
            templates = AppGenerator.list_templates()
            try:
                from src.core.template_engine import TemplateEngine
                templates["niche_templates"] = TemplateEngine().list_niches()
                templates["niche_domains"] = TemplateEngine().list_domains()
            except Exception:
                pass
            return templates
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/system/status")
    async def system_status():
        try:
            return await orchestrator.get_system_status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ════════════════════════════════════════════════════════
    #  PHASE 5: AUDIT EVENTS ENDPOINT
    # ════════════════════════════════════════════════════════

    @app.get("/v1/audit/events")
    async def query_audit_events(
        request: Request,
        tenant_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        auth_ctx: AuthContext = Depends(require_auth_dep),
    ):
        """Query audit events (Phase 5). Requires manager role."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager or admin required")
        audit = getattr(app.state, "audit_logger", None)
        if audit is None or not _AUDIT_AVAILABLE:
            raise HTTPException(status_code=501, detail="Audit logging not available")
        effective_tenant = tenant_id
        if not auth_ctx.has_role("admin"):
            effective_tenant = auth_ctx.tenant_id
        events = audit.query_events(
            tenant_id=effective_tenant, event_type=event_type, limit=min(limit, 1000),
        )
        return {"events": events, "total": len(events)}

    # ════════════════════════════════════════════════════════
    #  PHASE 5: LOGOUT ENDPOINT (always registered)
    # ════════════════════════════════════════════════════════

    @app.post("/v1/auth/logout")
    async def auth_logout(request: Request):
        """Logout: revoke the current access token (Phase 5)."""
        token_blacklist = getattr(app.state, "token_blacklist", None)
        if token_blacklist is None:
            return {"message": "Logout processed (blacklist not available)"}

        authorization = request.headers.get("Authorization", "")
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            try:
                import base64
                import json as _json

                parts = token.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                    jti = payload.get("jti", payload.get("sub", ""))
                    exp = payload.get("exp")
                    user_id = payload.get("sub")
                    token_blacklist.revoke_token(
                        jti=str(jti),
                        user_id=int(user_id) if user_id and user_id.isdigit() else None,
                        reason="logout",
                        expires_at=exp,
                    )
                    audit = getattr(app.state, "audit_logger", None)
                    if audit and _AUDIT_AVAILABLE:
                        audit.log_event(
                            event_type=AuditEventType.AUTH_TOKEN_REVOKED,
                            description=f"Token revoked on logout (jti={str(jti)[:8]})",
                            tenant_id=payload.get("tenant_id", "__anonymous__"),
                            user_id=int(user_id) if user_id and user_id.isdigit() else None,
                            ip_address=request.client.host if request.client else "",
                        )
            except Exception as e:
                logger.debug("Token revocation parsing failed: %s", e)

        return {"message": "Logged out successfully"}
