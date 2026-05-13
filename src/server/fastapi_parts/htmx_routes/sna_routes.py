"""
Zenic-Agents Asistente — SNA HTMX Routes (Enhanced)

Endpoints for SNA configuration:
- Page rendering (TemplateResponse)
- Status, monitor list, thresholds CRUD, test, start/stop
- Alert history (HTML partial)
- Real-time alert feed (HTML partial with HTMX polling)
- Monitor toggle with full 12-monitor support
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/htmx/sna", tags=["htmx-sna"])

# Template setup
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
_templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)
    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": "sna",
        "alert_count": 0,
    }
    ctx.update(context)
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        stats = sna.detailed_stats
        ctx["alert_count"] = stats.get("alert_manager", {}).get("active_alerts", 0)
    except Exception:
        pass
    return _templates.TemplateResponse(template_name, ctx)


# ── Page Route ─────────────────────────────────────────────

@router.get("/page", response_class=HTMLResponse)
async def sna_page(request: Request) -> HTMLResponse:
    """Render SNA configuration page."""
    return _render(request, "sna_config.html", {})


# ── Status ─────────────────────────────────────────────────

@router.get("/status", response_model=None)
async def get_sna_status(request: Request) -> Dict[str, Any]:
    """Get SNA status as JSON."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        stats = sna.detailed_stats
        return {
            "scheduler_state": stats.get("scheduler", {}).get("state", "STOPPED"),
            "active_monitors": stats.get("scheduler", {}).get("active_monitors", 0),
            "pending_alerts": stats.get("alert_manager", {}).get("active_alerts", 0),
            "checks_completed": stats.get("engine", {}).get("total_checks", 0),
        }
    except Exception:
        return {"scheduler_state": "STOPPED", "active_monitors": 0, "pending_alerts": 0, "checks_completed": 0}


# ── Monitors ───────────────────────────────────────────────

@router.get("/monitors-list", response_model=None)
async def get_monitors_json(request: Request) -> List[Dict[str, Any]]:
    """Get monitors as JSON for Alpine.js."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        monitors = sna.get_monitors().values()
        return [{"monitor_id": m.monitor_id,
                 "weight": m.weight.value if hasattr(m.weight, "value") else str(m.weight),
                 "interval": m.effective_interval if hasattr(m, "effective_interval") else 300,
                 "enabled": getattr(m, "enabled", True)}
                for m in monitors]
    except Exception:
        return []


@router.get("/monitors", response_model=None)
async def get_monitors_html(request: Request) -> str:
    """Get monitors as HTML table."""
    rows = ""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        monitors = list(sna.get_monitors().values())
        if not monitors:
            return '<tr><td colspan="5" class="text-center text-muted py-3">Sin monitores configurados</td></tr>'
        for m in monitors:
            mid = getattr(m, "monitor_id", "--")
            weight = getattr(m, "weight", "lightweight")
            wv = weight.value if hasattr(weight, "value") else str(weight)
            interval = getattr(m, "effective_interval", 300)
            enabled = getattr(m, "enabled", True)
            status_cls = "bg-success" if enabled else "bg-danger"
            status_txt = "Activo" if enabled else "Inactivo"
            rows += (f'<tr><td class="font-monospace">{mid}</td>'
                     f'<td><span class="badge bg-info">{wv}</span></td>'
                     f'<td>{interval}s</td>'
                     f'<td><span class="badge {status_cls}">{status_txt}</span></td>'
                     f'<td><button class="btn btn-sm btn-outline-warning" '
                     f'hx-post="/htmx/sna/toggle/{mid}" hx-swap="none" hx-trigger="click">Toggle</button></td></tr>')
    except Exception:
        rows = '<tr><td colspan="5" class="text-center text-muted py-3">Error cargando monitores</td></tr>'
    return (
        '<table class="table table-hover mb-0">'
        '<thead><tr><th>ID</th><th>Peso</th><th>Intervalo</th><th>Estado</th><th>Acción</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


# ── Thresholds ─────────────────────────────────────────────

@router.get("/thresholds", response_model=None)
async def get_thresholds_html(request: Request) -> str:
    """Get thresholds as HTML table."""
    rows = ""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        thresholds = sna._threshold_engine.get_thresholds()
        if not thresholds:
            return '<tr><td colspan="5" class="text-center text-muted py-3">Sin umbrales configurados</td></tr>'
        for t in thresholds:
            tid = getattr(t, "threshold_id", "--")
            field = getattr(t, "field_name", "--")
            op = getattr(t, "operator", "gt")
            op = op.value if hasattr(op, "value") else str(op)
            val = getattr(t, "value", 0)
            cd = getattr(t, "cooldown_seconds", 300)
            rows += (f'<tr><td class="font-monospace">{tid}</td><td>{field}</td><td>{op} {val}</td>'
                     f'<td>{cd}s</td><td><button class="btn btn-sm btn-outline-danger" '
                     f'hx-delete="/htmx/sna/thresholds/{tid}" hx-swap="none">Eliminar</button></td></tr>')
    except Exception:
        rows = '<tr><td colspan="5" class="text-center text-muted py-3">Error cargando umbrales</td></tr>'
    return (
        '<table class="table table-hover mb-0">'
        '<thead><tr><th>ID</th><th>Campo</th><th>Condición</th><th>Cooldown</th><th>Acción</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


@router.post("/thresholds", response_model=None)
async def add_threshold(request: Request) -> Dict[str, Any]:
    """Add a new threshold."""
    body = await request.json()
    try:
        from src.core.sna import get_sna_engine, ThresholdConfig, ThresholdOperator
        sna = get_sna_engine()
        op_map = {"gt": ThresholdOperator.GT, "gte": ThresholdOperator.GTE,
                  "lt": ThresholdOperator.LT, "lte": ThresholdOperator.LTE,
                  "eq": ThresholdOperator.EQ}
        tc = ThresholdConfig(
            monitor_id=body.get("monitor_id", ""),
            field_name=body.get("field_name", "value"),
            operator=op_map.get(body.get("operator", "gt"), ThresholdOperator.GT),
            value=float(body.get("value", 100)),
            cooldown_seconds=int(body.get("cooldown", 300)),
        )
        sna.add_threshold(tc)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Add threshold failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.delete("/thresholds/{threshold_id}", response_model=None)
async def delete_threshold(threshold_id: str) -> Dict[str, Any]:
    """Delete a threshold."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        sna._threshold_engine.remove_threshold(threshold_id)
        return {"status": "ok"}
    except Exception:
        return {"status": "error"}


# ── Test & Control ─────────────────────────────────────────

@router.post("/test/{monitor_id}", response_model=None)
async def test_monitor(monitor_id: str) -> Dict[str, Any]:
    """Run a manual monitor test."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        result = await sna.check_monitor(monitor_id)
        if result is None:
            return {"triggered": False, "detail": "Monitor not found"}
        return {
            "triggered": result.triggered if hasattr(result, "triggered") else False,
            "detail": getattr(result, "detail", "Test complete"),
            "value": getattr(result, "value", None),
        }
    except Exception as exc:
        return {"triggered": False, "detail": f"Error: {exc}"}


@router.post("/start", response_model=None)
async def start_sna() -> Dict[str, Any]:
    """Start the SNA engine."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        await sna.start()
        return {"status": "started"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/stop", response_model=None)
async def stop_sna() -> Dict[str, Any]:
    """Stop the SNA engine."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        await sna.stop()
        return {"status": "stopped"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/toggle/{monitor_id}", response_model=None)
async def toggle_monitor(monitor_id: str) -> Dict[str, Any]:
    """Toggle a monitor on/off."""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        monitors = sna.get_monitors()
        config = monitors.get(monitor_id)
        if config is None:
            return {"status": "error", "message": "Monitor not found"}
        config.enabled = not getattr(config, "enabled", True)
        sna.add_monitor(config)
        return {"status": "ok", "enabled": config.enabled}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Alert History ──────────────────────────────────────────

@router.get("/alert-history", response_model=None)
async def get_alert_history(request: Request) -> str:
    """Return alert history as HTML table partial."""
    rows = ""
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        history = sna.get_alert_history(limit=20) if hasattr(sna, "get_alert_history") else []
        if history:
            for h in history:
                h_dict = h.to_dict() if hasattr(h, "to_dict") else (h if isinstance(h, dict) else {})
                sev = h_dict.get("severity", "info")
                sev_cls = {"warning": "bg-warning text-dark", "critical": "bg-danger"}.get(sev, "bg-info")
                ts = h_dict.get("timestamp", "")
                detail = h_dict.get("detail", h_dict.get("message", ""))
                monitor = h_dict.get("monitor_id", "--")
                rows += (
                    f'<tr><td class="small">{ts}</td>'
                    f'<td class="font-monospace small">{monitor}</td>'
                    f'<td><span class="badge {sev_cls}">{sev.upper()}</span></td>'
                    f'<td class="small">{detail}</td></tr>'
                )
    except Exception:
        rows = '<tr><td colspan="4" class="text-center text-muted py-3">Error cargando historial</td></tr>'

    if not rows:
        rows = '<tr><td colspan="4" class="text-center text-muted py-3">Sin historial de alertas</td></tr>'

    return (
        '<table class="table table-hover mb-0">'
        '<thead><tr><th>Timestamp</th><th>Monitor</th><th>Severidad</th><th>Detalle</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


# ── Real-Time Alert Feed ──────────────────────────────────

@router.get("/realtime-alerts", response_model=None)
async def get_realtime_alerts(request: Request) -> str:
    """Return real-time alert feed as HTML partial (polled every 10s)."""
    items_html = '<p class="text-muted"><i class="bi bi-check-circle me-1"></i>Todos los monitores OK</p>'

    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        alerts = sna.get_active_alerts()
        if alerts:
            lines = []
            for a in alerts[:5]:
                sev = getattr(a, "severity", None)
                sev = sev.value if hasattr(sev, "value") else str(sev or "info")
                detail = getattr(a, "detail", "")
                sev_class = {"warning": "bg-warning text-dark", "critical": "bg-danger zenic-alert-severity-critical"}.get(sev, "bg-info")
                lines.append(
                    f'<div class="zenic-alert-feed-item zenic-fade-in">'
                    f'<span class="badge {sev_class}">{sev.upper()}</span> '
                    f'<span class="small">{detail}</span></div>'
                )
            items_html = "".join(lines)
    except Exception:
        pass

    return items_html


def register_sna_htmx_routes(app: Any) -> None:
    """Register SNA HTMX routes on the FastAPI app."""
    app.include_router(router)
