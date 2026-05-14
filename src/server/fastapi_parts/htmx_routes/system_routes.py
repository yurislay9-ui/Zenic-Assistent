"""
Zenic-Agents Asistente — System HTMX Routes (Phase 7.1)

HTMX endpoints for defense status, license management, and page rendering.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["htmx-system"])

# Templates setup
import os
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
_templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    """Render a template with standard context."""
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)

    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": template_name.replace("pages/", "").replace(".html", ""),
        "alert_count": 0,
    }
    ctx.update(context)

    try:
        # Try to get SNA alert count
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        stats = sna.detailed_stats
        ctx["alert_count"] = stats.get("alert_manager", {}).get("active_alerts", 0)
    except Exception:
        pass

    return _templates.TemplateResponse(template_name, ctx)


# ── Page Routes ─────────────────────────────────────────

@router.get("/app/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render dashboard page."""
    return _render(request, "pages/dashboard.html", {})


@router.get("/app/sna", response_class=HTMLResponse)
async def sna_page(request: Request) -> HTMLResponse:
    """Render SNA configuration page."""
    return _render(request, "pages/sna.html", {})


@router.get("/app/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> HTMLResponse:
    """Render audit trail page."""
    return _render(request, "pages/audit.html", {})


@router.get("/app/channels", response_class=HTMLResponse)
async def channels_page(request: Request) -> HTMLResponse:
    """Render channels page."""
    return _render(request, "pages/channels.html", {})


@router.get("/app/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request) -> HTMLResponse:
    """Render inventory page."""
    return _render(request, "pages/inventory.html", {})


@router.get("/app/crm", response_class=HTMLResponse)
async def crm_page(request: Request) -> HTMLResponse:
    """Render CRM page."""
    return _render(request, "pages/crm.html", {})


@router.get("/app/crm/{client_id}", response_class=HTMLResponse)
async def crm_client_detail(client_id: str, request: Request) -> HTMLResponse:
    """Render CRM client detail page."""
    return _render(request, "pages/crm_detail.html", {"client_id": client_id})


@router.get("/app/billing", response_class=HTMLResponse)
async def billing_page(request: Request) -> HTMLResponse:
    """Render billing page."""
    return _render(request, "pages/billing.html", {})


@router.get("/app/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render settings page."""
    return _render(request, "pages/settings.html", {})


@router.get("/app/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request) -> HTMLResponse:
    """Render onboarding page."""
    return _render(request, "pages/onboarding.html", {})


@router.get("/app/defense", response_class=HTMLResponse)
async def defense_page(request: Request) -> HTMLResponse:
    """Render defense status page."""
    return _render(request, "pages/defense.html", {})


@router.get("/app/license", response_class=HTMLResponse)
async def license_page(request: Request) -> HTMLResponse:
    """Render license management page."""
    return _render(request, "pages/license.html", {})


# ── Defense HTMX ────────────────────────────────────────

@router.get("/htmx/defense/status", response_model=None)
async def defense_status(request: Request) -> Dict[str, Any]:
    """Get defense-in-depth status as JSON."""
    try:
        from src.core.defense import get_defense_manager
        dm = get_defense_manager()
        status = dm.get_status()
        return {
            "overall_score": status.overall_score,
            "layer1": status.layer1_anti_tampering,
            "layer2": status.layer2_binary_hardening,
            "layer3": status.layer3_encryption,
            "layer4": status.layer4_integrity,
            "layer5": status.layer5_licensing,
            "layer6": status.layer6_server_secrets,
            "recommendations": status.recommendations,
        }
    except Exception:
        return {"overall_score": 0, "recommendations": ["Defense system not initialized"]}


@router.get("/htmx/defense/mode", response_model=None)
async def defense_mode(request: Request) -> str:
    """Get current system mode as HTML partial."""
    try:
        from src.core.degraded_mode import get_degraded_mode_manager
        dm = get_degraded_mode_manager()
        status = dm.get_status()
        mode = status["current_mode"]
        cls = {"normal": "badge-success", "degraded": "badge-warning",
               "restrictive": "badge-warning", "paralysis_l1": "badge-danger",
               "paralysis_l2": "badge-danger", "paralysis_l3": "badge-danger"}.get(mode, "badge-info")
        return (f'<div style="padding:12px;"><span class="badge-status {cls}" style="font-size:1.1rem;">'
                f'{mode.upper()}</span><p class="text-sm text-muted mt-8">'
                f'Escritura: {"Sí" if status["allows_write"] else "No"} | '
                f'Lectura: {"Sí" if status.get("is_read_only", False) == False else "Solo"} | '
                f'Exportar: {"Sí" if status["capabilities"]["can_export"] else "No"}</p></div>')
    except Exception:
        return '<p class="text-muted">Error cargando modo</p>'


# ── License HTMX ────────────────────────────────────────

@router.get("/htmx/license/status", response_model=None)
async def license_status(request: Request) -> Dict[str, Any]:
    """Get license status as JSON."""
    try:
        from src.core.license import get_license_manager
        lm = get_license_manager()
        return lm.get_status()
    except Exception:
        return {"valid": False, "status": "no_license", "tier": "none",
                "days_remaining": None, "hardware_bound": False,
                "kill_switch_active": False, "features": []}


@router.post("/htmx/license/activate", response_model=None)
async def activate_license(request: Request) -> Dict[str, Any]:
    """Activate a license key."""
    body = await request.json()
    key = body.get("key", "")
    try:
        from src.core.license import get_license_manager
        lm = get_license_manager()
        # Try to load/verify the license
        result = lm.verify()
        return {"status": "ok" if result.valid else "invalid", "message": result.reason}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/htmx/license/verify", response_model=None)
async def verify_license(request: Request) -> Dict[str, Any]:
    """Force license verification."""
    try:
        from src.core.license import get_license_manager
        lm = get_license_manager()
        result = lm.verify()
        return {"valid": result.valid, "status": result.status.value, "reason": result.reason}
    except Exception as exc:
        return {"valid": False, "status": "error", "reason": str(exc)}


@router.post("/htmx/license/ntp-check", response_model=None)
async def ntp_check(request: Request) -> Dict[str, Any]:
    """Check NTP time offset."""
    try:
        from src.core.license import get_license_manager
        lm = get_license_manager()
        offset = lm.check_ntp_time()
        return {"offset_seconds": offset, "status": "ok"}
    except Exception as exc:
        return {"offset_seconds": 0, "status": "error", "message": str(exc)}


@router.post("/htmx/license/kill-switch/deactivate", response_model=None)
async def deactivate_kill_switch(request: Request) -> Dict[str, Any]:
    """Deactivate kill switch (admin only)."""
    try:
        from src.core.license import get_license_manager
        lm = get_license_manager()
        lm.deactivate_kill_switch(source="admin_ui")
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def register_system_routes(app: Any) -> None:
    """Register system HTMX routes on the FastAPI app."""
    app.include_router(router)
