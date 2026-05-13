"""
Middleware setup for the FastAPI application.

Registers CORS, security headers, metrics, rate-limiting, and the
tenant-context injection middleware on the FastAPI app instance.
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    os,
    time,
    uuid,
    logging,
    logger,
    AuthContext,
    build_overloaded_response,
    set_current_tenant,
    clear_current_tenant,
    PLAN_DEFINITIONS,
    resolve_auth,
    _TRACING_AVAILABLE,
    _METRICS_AVAILABLE,
    _AUDIT_AVAILABLE,
    _HEALTH_AVAILABLE,
    _SECURITY_AVAILABLE,
    _OPEN_DESIGN_AVAILABLE,
)
from src.server.fastapi_parts._helpers import _build_tenant_context, make_auth_dependencies

# Re-export availability flags for external consumers
__all__ = [
    "setup_middleware",
    "make_auth_dependencies",
    "_TRACING_AVAILABLE",
    "_METRICS_AVAILABLE",
    "_AUDIT_AVAILABLE",
    "_HEALTH_AVAILABLE",
    "_SECURITY_AVAILABLE",
    "_OPEN_DESIGN_AVAILABLE",
]


# ────────────────────────────────────────────────────────────
#  Middleware & service initialisation
# ────────────────────────────────────────────────────────────

def setup_middleware(
    app: Any,
    *,
    orchestrator: Any,
    auth_service: Optional[Any],
    rate_limiter: Optional[Any],
    governor: Optional[Any],
    start_time: float,
) -> None:
    """Attach all middleware and initialise observability services on *app*."""

    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    # ── CORS ────────────────────────────────────────────────
    cors_origins = os.getenv("ZENIC_CORS_ORIGINS", "*")
    cors_origins_list = (
        [o.strip() for o in cors_origins.split(",") if o.strip()]
        if cors_origins != "*"
        else ["*"]
    )
    cors_credentials_env = (
        os.getenv("ZENIC_CORS_CREDENTIALS", "true").lower() == "true"
    )

    # Merge Open Design origins BEFORE adding middleware
    if _OPEN_DESIGN_AVAILABLE:
        from src.server.fastapi_parts._imports import get_open_design_config

        od_config = get_open_design_config()
        if od_config.open_design_origins and cors_origins_list != ["*"]:
            for origin in od_config.open_design_origins:
                if origin not in cors_origins_list:
                    cors_origins_list.append(origin)

    cors_credentials = cors_credentials_env if cors_origins_list != ["*"] else False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_list,
        allow_credentials=cors_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS: origins=%s, credentials=%s", cors_origins_list, cors_credentials)

    # ── Security middleware ─────────────────────────────────
    if _SECURITY_AVAILABLE:
        from src.server.fastapi_parts._imports import (
            SecurityConfig, create_security_middleware, TokenBlacklist,
        )
        security_config = SecurityConfig.from_env()
        app.middleware("http")(create_security_middleware(security_config))
        app.state.security_config = security_config
        app.state.token_blacklist = TokenBlacklist(security_config.token_blacklist_db)
        logger.info(
            "Security: middleware enabled (CSP=%s, HSTS=%s, auth_rate_limit=%dRPM)",
            security_config.enable_csp, security_config.enable_hsts,
            security_config.auth_rate_limit_rpm,
        )
    else:
        app.state.security_config = None
        app.state.token_blacklist = None

    # ── Metrics middleware ──────────────────────────────────
    if _METRICS_AVAILABLE:
        from src.server.fastapi_parts._imports import (
            MetricsConfig, get_metrics_collector, metrics_middleware,
        )
        _metrics = get_metrics_collector(MetricsConfig.from_env())
        app.middleware("http")(metrics_middleware)
        app.state.metrics_collector = _metrics
        logger.info(
            "Metrics: Prometheus collector initialized (prometheus_client=%s)",
            _metrics.is_prometheus_available,
        )
    else:
        app.state.metrics_collector = None

    # ── Tracing ─────────────────────────────────────────────
    if _TRACING_AVAILABLE:
        from src.server.fastapi_parts._imports import TracingConfig, init_tracing

        tracing_initialized = init_tracing(TracingConfig.from_env())
        logger.info("Tracing: OpenTelemetry=%s", tracing_initialized)

    # ── Audit logger ────────────────────────────────────────
    if _AUDIT_AVAILABLE:
        from src.server.fastapi_parts._imports import get_audit_logger

        _audit = get_audit_logger()
        app.state.audit_logger = _audit
        logger.info("Audit: logger initialized (DB=%s)", _audit._initialized)
    else:
        app.state.audit_logger = None

    # ── Health aggregator ───────────────────────────────────
    if _HEALTH_AVAILABLE:
        from src.server.fastapi_parts._imports import (
            get_health_aggregator,
            check_orchestrator, check_auth_db, check_resources, check_disk_space,
        )
        _health_agg = get_health_aggregator()
        _health_agg.register_liveness_check("orchestrator", lambda: check_orchestrator(orchestrator))
        _health_agg.register_liveness_check("resources", lambda: check_resources(governor))
        _health_agg.register_readiness_check("orchestrator", lambda: check_orchestrator(orchestrator))
        _health_agg.register_readiness_check("auth_db", lambda: check_auth_db(auth_service))
        _health_agg.register_readiness_check("resources", lambda: check_resources(governor))
        _health_agg.register_readiness_check("disk", lambda: check_disk_space("."))
        app.state.health_aggregator = _health_agg
        logger.info(
            "Health: aggregator initialized (liveness=%d, readiness=%d)",
            len(_health_agg._liveness_checks), len(_health_agg._readiness_checks),
        )
    else:
        app.state.health_aggregator = None

    # ── Open Design Integration ─────────────────────────────
    if _OPEN_DESIGN_AVAILABLE:
        from src.server.fastapi_parts._imports import get_open_design_config

        _od_config = get_open_design_config()
        app.state.open_design_config = _od_config
        logger.info(
            "OpenDesign: integration enabled (SSE=%s, visual_bypass=%s, origins=%s)",
            _od_config.sse_enabled,
            _od_config.visual_bypass_enabled,
            _od_config.open_design_origins,
        )
    else:
        app.state.open_design_config = None

    # ── Distributed coordination backend ────────────────────
    try:
        from src.core.distributed import (
            CoordinationBackend, BackendConfig, DistributedTaskQueue,
        )
        _backend_config = BackendConfig()
        db_url = os.getenv("DATABASE_URL", "")
        if db_url and ("postgresql" in db_url or "postgres" in db_url):
            from src.core.distributed.backend import BackendType
            _backend_config = BackendConfig(
                backend_type=BackendType.POSTGRESQL, connection_string=db_url,
            )
        _coord_backend = CoordinationBackend.create(_backend_config)
        app.state.coordination_backend = _coord_backend
        app.state.task_queue = DistributedTaskQueue(backend=_coord_backend)
        logger.info(
            "Distributed: coordination backend initialized (type=%s)",
            type(_coord_backend).__name__,
        )
    except Exception as e:
        logger.warning(
            "Distributed: backend initialization failed (%s) — Phase 4 endpoints disabled", e,
        )
        app.state.coordination_backend = None
        app.state.task_queue = None

    # ── Rate-limit + tenant context middleware ───────────────
    _register_rate_limit_middleware(
        app,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
    )


# ────────────────────────────────────────────────────────────
#  Rate-limit & tenant-context middleware (inner)
# ────────────────────────────────────────────────────────────

def _register_rate_limit_middleware(
    app: Any,
    *,
    auth_service: Optional[Any],
    rate_limiter: Optional[Any],
    governor: Optional[Any],
) -> None:
    """Register the per-request middleware that handles rate limiting,
    tenant-context injection, governor checks, and usage tracking."""

    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def rate_limit_and_governor(request, call_next):  # type: ignore[no-untyped-def]
        """Per-request middleware: tenant context, rate limiting, governor, usage tracking."""
        skip_paths = {"/docs", "/redoc", "/openapi.json", "/health", "/ready", "/metrics"}
        if request.url.path in skip_paths:
            return await call_next(request)

        # Resolve auth for rate limiting
        auth_ctx: Optional[AuthContext] = None
        if auth_service is not None:
            authorization = request.headers.get("Authorization", "")
            api_key = request.headers.get("X-API-Key", "")
            auth_ctx = resolve_auth(auth_service, authorization or None, api_key or None)

        tenant_ctx = _build_tenant_context(auth_ctx, auth_service)
        set_current_tenant(tenant_ctx)
        request.state.tenant_ctx = tenant_ctx
        request.state.auth_ctx = auth_ctx

        try:
            # Rate limiting
            if rate_limiter is not None:
                client_ip = request.client.host if request.client else "0.0.0.0"
                user_id = auth_ctx.user_id if auth_ctx else None
                tenant_id = auth_ctx.tenant_id if auth_ctx else None

                if auth_ctx and tenant_id:
                    tenant = auth_service.get_tenant(tenant_id) if auth_service else None
                    if tenant:
                        plan = tenant.get("plan", "free")
                        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
                        if hasattr(rate_limiter, "set_user_limits"):
                            rate_limiter.set_user_limits(
                                user_id,
                                rpm=quotas.get("max_requests_per_minute", 10),
                                burst=min(quotas.get("max_requests_per_minute", 10), 20),
                            )
                        if hasattr(rate_limiter, "set_tenant_limits"):
                            rate_limiter.set_tenant_limits(
                                tenant_id,
                                rpm=quotas.get("max_requests_per_minute", 10),
                            )

                        # Check daily quota
                        if auth_service and hasattr(auth_service, "check_tenant_quota"):
                            quota_check = auth_service.check_tenant_quota(tenant_id)
                            if not quota_check.get("allowed", True):
                                return JSONResponse(
                                    status_code=429,
                                    content={
                                        "error": {
                                            "message": quota_check.get("reason", "Quota exceeded"),
                                            "type": "quota_exceeded",
                                            "plan": plan,
                                        }
                                    },
                                )

                        # Check storage quota
                        if auth_service and hasattr(auth_service, "check_storage_quota"):
                            storage_check = auth_service.check_storage_quota(tenant_id)
                            if not storage_check.get("allowed", True):
                                return JSONResponse(
                                    status_code=429,
                                    content={
                                        "error": {
                                            "message": (
                                                f"Storage quota exceeded "
                                                f"({storage_check.get('used_mb', 0):.1f}MB / "
                                                f"{storage_check.get('max_mb', 0)}MB)"
                                            ),
                                            "type": "storage_quota_exceeded",
                                            "plan": plan,
                                        }
                                    },
                                )

                if hasattr(rate_limiter, "acquire"):
                    allowed = rate_limiter.acquire(client_ip, user_id=user_id, tenant_id=tenant_id)
                    if not allowed:
                        return JSONResponse(
                            status_code=429,
                            content={"error": {"message": "Rate limit exceeded", "type": "rate_limit_exceeded"}},
                        )

            # Governor check (headless mode)
            if governor is not None:
                governor.pre_request()
                if governor.is_ram_critical():
                    if rate_limiter and hasattr(rate_limiter, "release"):
                        rate_limiter.release()
                    return JSONResponse(status_code=503, content=build_overloaded_response())

            # Process request and measure time
            request_start = time.time()
            try:
                with app.state._request_count_lock:
                    app.state.request_count += 1
                response = await call_next(request)
            finally:
                processing_time_ms = int((time.time() - request_start) * 1000)
                if (
                    auth_ctx
                    and auth_ctx.tenant_id
                    and auth_service
                    and hasattr(auth_service, "record_usage")
                ):
                    try:
                        compute_seconds = processing_time_ms / 1000.0
                        prompt_words = 0
                        completion_words = 0
                        try:
                            prompt_words = int(request.headers.get("content-length", "0")) // 5
                            if hasattr(response, "body") and response.body:
                                completion_words = len(response.body) // 5
                        except (ValueError, TypeError):
                            pass
                        tokens = int((prompt_words + completion_words) * 1.15)
                        auth_service.record_usage(
                            auth_ctx.tenant_id,
                            requests=1,
                            tokens=tokens,
                            compute_seconds=compute_seconds,
                        )
                    except Exception as e:
                        logger.debug("Usage recording failed: %s", e)

                # Log request with tenant_id
                try:
                    from src.core.shared.db_initializer import get_connection

                    log_conn = get_connection("request_log.sqlite")
                    log_conn.execute(
                        "INSERT INTO requests (request_id, model, operation, route, status, processing_time_ms, tenant_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            "zenic-agents",
                            request.method,
                            request.url.path,
                            "completed",
                            processing_time_ms,
                            tenant_ctx.effective_tenant_id,
                        ),
                    )
                    log_conn.commit()
                except Exception as e:
                    logger.debug("Request logging failed: %s", e)

                if governor is not None:
                    governor.post_request()
                if rate_limiter is not None and hasattr(rate_limiter, "release"):
                    rate_limiter.release()

            return response
        finally:
            clear_current_tenant()
