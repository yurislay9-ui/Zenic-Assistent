"""
SNA (Sistema Nervioso Autónomo) API endpoints.

Phase 4: /v1/sna/* routes for proactive monitoring management.
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    logging,
    logger,
)

def register_sna_routes(
    app: Any,
    *,
    auth_service: Optional[Any],
    require_auth_dep: Any,
) -> None:
    """Register SNA monitoring and alert endpoints on *app*."""

    from fastapi import Request, HTTPException, Depends
    from fastapi.responses import JSONResponse

    # ════════════════════════════════════════════════════════
    #  SNA Engine Status
    # ════════════════════════════════════════════════════════

    @app.get("/v1/sna/status")
    async def sna_status():
        """Get SNA engine status and statistics."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            return engine.detailed_stats
        except Exception as e:
            logger.error("SNA status error: %s", e)
            return {"status": "error", "error": str(e)}

    # ════════════════════════════════════════════════════════
    #  Monitor Management
    # ════════════════════════════════════════════════════════

    @app.get("/v1/sna/monitors")
    async def list_monitors():
        """List all registered SNA monitors and their configurations."""
        try:
            from src.core.sna import get_sna_engine, get_all_monitor_ids
            engine = get_sna_engine()
            configs = engine.get_monitors()
            all_ids = get_all_monitor_ids()
            return {
                "active_monitors": [
                    {
                        "monitor_id": mid,
                        "monitor_name": cfg.monitor_name,
                        "weight": cfg.weight.value,
                        "interval_seconds": cfg.effective_interval,
                        "enabled": cfg.enabled,
                        "priority": cfg.priority,
                    }
                    for mid, cfg in configs.items()
                ],
                "available_monitors": all_ids,
                "total_active": len(configs),
                "total_available": len(all_ids),
            }
        except Exception as e:
            logger.error("SNA monitors list error: %s", e)
            return {"active_monitors": [], "available_monitors": [], "error": str(e)}

    @app.post("/v1/sna/monitors/{monitor_id}/enable")
    async def enable_monitor(monitor_id: str):
        """Enable a specific SNA monitor."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            engine._scheduler.enable_monitor(monitor_id)
            return {"status": "enabled", "monitor_id": monitor_id}
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/v1/sna/monitors/{monitor_id}/disable")
    async def disable_monitor(monitor_id: str):
        """Disable a specific SNA monitor."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            engine._scheduler.disable_monitor(monitor_id)
            return {"status": "disabled", "monitor_id": monitor_id}
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/v1/sna/monitors/{monitor_id}/check")
    async def manual_check(monitor_id: str, request: Request):
        """Manually trigger a monitor check."""
        try:
            body = {}
            try:
                body = await request.json()
            except Exception:
                pass
            tenant_id = body.get("tenant_id", "")
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            result = await engine.check_monitor(monitor_id, tenant_id)
            if result is None:
                raise HTTPException(status_code=404, detail=f"Monitor '{monitor_id}' not found")
            return {
                "monitor_id": result.monitor_id,
                "monitor_name": result.monitor_name,
                "triggered": result.triggered,
                "value": result.value,
                "detail": result.detail,
                "severity": result.severity.value,
                "duration_ms": result.duration_ms,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("SNA manual check error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/sna/check-all")
    async def check_all_monitors(request: Request):
        """Run all active monitors once."""
        try:
            body = {}
            try:
                body = await request.json()
            except Exception:
                pass
            tenant_id = body.get("tenant_id", "")
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            results = await engine.check_all(tenant_id)
            return {
                "results": [
                    {
                        "monitor_id": r.monitor_id,
                        "triggered": r.triggered,
                        "detail": r.detail,
                        "severity": r.severity.value,
                        "duration_ms": r.duration_ms,
                    }
                    for r in results
                ],
                "total": len(results),
                "triggered": sum(1 for r in results if r.triggered),
            }
        except Exception as e:
            logger.error("SNA check-all error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ════════════════════════════════════════════════════════
    #  Alert Management
    # ════════════════════════════════════════════════════════

    @app.get("/v1/sna/alerts")
    async def list_alerts(request: Request):
        """Get active SNA alerts."""
        try:
            tenant_id = request.query_params.get("tenant_id", "")
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            alerts = engine.get_active_alerts(tenant_id)
            return {
                "alerts": [
                    {
                        "alert_id": a.alert_id,
                        "monitor_id": a.monitor_id,
                        "monitor_name": a.monitor_name,
                        "severity": a.severity.value,
                        "status": a.status.value,
                        "title": a.title,
                        "message": a.message,
                        "channel": a.channel,
                        "created_at": a.created_at,
                    }
                    for a in alerts
                ],
                "total": len(alerts),
            }
        except Exception as e:
            logger.error("SNA alerts list error: %s", e)
            return {"alerts": [], "total": 0, "error": str(e)}

    @app.post("/v1/sna/alerts/{alert_id}/acknowledge")
    async def acknowledge_alert(alert_id: str):
        """Acknowledge an SNA alert."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            engine.acknowledge_alert(alert_id)
            return {"status": "acknowledged", "alert_id": alert_id}
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/v1/sna/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str, request: Request):
        """Resolve an SNA alert."""
        try:
            body = {}
            try:
                body = await request.json()
            except Exception:
                pass
            monitor_id = body.get("monitor_id", "")
            tenant_id = body.get("tenant_id", "")
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            engine.resolve_alert(alert_id, monitor_id, tenant_id)
            return {"status": "resolved", "alert_id": alert_id}
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ════════════════════════════════════════════════════════
    #  Threshold Management
    # ════════════════════════════════════════════════════════

    @app.get("/v1/sna/thresholds")
    async def list_thresholds(request: Request):
        """Get configured SNA thresholds."""
        try:
            monitor_id = request.query_params.get("monitor_id", "")
            tenant_id = request.query_params.get("tenant_id", "")
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            thresholds = engine._threshold_engine.get_thresholds(monitor_id, tenant_id)
            return {
                "thresholds": [
                    {
                        "threshold_id": t.threshold_id,
                        "monitor_id": t.monitor_id,
                        "field_name": t.field_name,
                        "operator": t.operator.value,
                        "value": t.value,
                        "severity": t.severity.value,
                        "cooldown_seconds": t.cooldown_seconds,
                    }
                    for t in thresholds
                ],
                "total": len(thresholds),
            }
        except Exception as e:
            logger.error("SNA thresholds list error: %s", e)
            return {"thresholds": [], "total": 0, "error": str(e)}

    @app.post("/v1/sna/thresholds")
    async def add_threshold(request: Request):
        """Add a new SNA threshold."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        try:
            from src.core.sna import ThresholdConfig, ThresholdOperator, AlertSeverity
            threshold = ThresholdConfig(
                threshold_id=body.get("threshold_id", f"th_{id(body):x}"),
                monitor_id=body["monitor_id"],
                field_name=body.get("field_name", "value"),
                operator=ThresholdOperator(body.get("operator", "gte")),
                value=float(body["value"]),
                value_high=float(body["value_high"]) if "value_high" in body else None,
                severity=AlertSeverity(body.get("severity", "warning")),
                cooldown_seconds=float(body.get("cooldown_seconds", 300)),
                tenant_id=body.get("tenant_id", ""),
                blueprint_name=body.get("blueprint_name", ""),
            )
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            engine._threshold_engine.add_threshold(threshold)
            return {"status": "created", "threshold_id": threshold.threshold_id}
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f"Missing field: {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid value: {e}")

    # ════════════════════════════════════════════════════════
    #  SNA Lifecycle Control
    # ════════════════════════════════════════════════════════

    @app.post("/v1/sna/start")
    async def start_sna():
        """Start the SNA engine."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            if not engine.get_monitors():
                engine.load_default_monitors()
            await engine.start()
            return {"status": "started", "monitors": len(engine.get_monitors())}
        except Exception as e:
            logger.error("SNA start error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/sna/stop")
    async def stop_sna():
        """Stop the SNA engine."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            await engine.stop()
            return {"status": "stopped"}
        except Exception as e:
            logger.error("SNA stop error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/sna/pause")
    async def pause_sna():
        """Pause the SNA engine."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            await engine.pause()
            return {"status": "paused"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/sna/resume")
    async def resume_sna():
        """Resume the SNA engine."""
        try:
            from src.core.sna import get_sna_engine
            engine = get_sna_engine()
            await engine.resume()
            return {"status": "resumed"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("SNA routes registered: /v1/sna/*")
