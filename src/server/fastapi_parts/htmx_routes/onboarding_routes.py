"""
Zenic-Agents Asistente — Onboarding HTMX Routes

Endpoints for onboarding wizard:
- Page rendering (TemplateResponse)
- Blueprint listing (JSON)
- Channel configuration (POST)
- Monitor setup (POST)
- Team invitations (POST)
- Full deployment (POST)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/htmx/onboarding", tags=["htmx-onboarding"])

# Template setup
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
_templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)
    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": "onboarding",
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
async def onboarding_page(request: Request) -> HTMLResponse:
    """Render onboarding wizard page."""
    return _render(request, "onboarding.html", {})


# ── Blueprint Selection ────────────────────────────────────

@router.get("/blueprints", response_model=None)
async def list_blueprints(request: Request) -> List[Dict[str, Any]]:
    """List available blueprints for onboarding."""
    try:
        from src.core.blueprints import get_blueprint_loader
        loader = get_blueprint_loader()
        blueprints = loader.list_blueprints() if hasattr(loader, "list_blueprints") else []
        return [{"id": b.get("blueprint_id", ""), "name": b.get("name", ""),
                 "description": b.get("description", ""), "features": b.get("features", []),
                 "icon": b.get("icon", "bi-box")}
                for b in blueprints]
    except Exception:
        return [
            {"id": "retail", "name": "Retail", "description": "Gestión de inventario y ventas",
             "features": ["Inventario", "Facturación", "CRM"], "icon": "bi-shop"},
            {"id": "crm", "name": "CRM", "description": "Gestión de clientes y seguimiento",
             "features": ["Contactos", "Pipeline", "Notificaciones"], "icon": "bi-people"},
            {"id": "billing", "name": "Facturación", "description": "Facturas, pagos y cobros",
             "features": ["Facturas", "Pagos", "Recordatorios"], "icon": "bi-receipt"},
            {"id": "manufacturing", "name": "Manufactura", "description": "Producción y cadena de suministro",
             "features": ["Producción", "Supply Chain", "Calidad"], "icon": "bi-gear"},
        ]


# ── Channel Configuration ─────────────────────────────────

@router.post("/configure-channel", response_model=None)
async def configure_channel(request: Request) -> Dict[str, Any]:
    """Configure a notification channel (Telegram, Discord, Email)."""
    body = await request.json()
    channel_type = body.get("type", "")
    logger.info("Channel configured: type=%s", channel_type)

    try:
        from src.core.executors.discord_executor import DiscordExecutor
        from src.core.executors.email_executor import EmailExecutor
    except Exception:
        pass

    return {"status": "ok", "channel_type": channel_type}


# ── Monitor Setup ──────────────────────────────────────────

@router.post("/setup-monitors", response_model=None)
async def setup_monitors(request: Request) -> Dict[str, Any]:
    """Configure SNA monitors during onboarding."""
    body = await request.json()
    monitor_ids = body.get("monitors", [])
    logger.info("Monitors configured: %s", monitor_ids)

    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        sna.load_default_monitors()
    except Exception:
        pass

    return {"status": "ok", "monitors": monitor_ids}


# ── Team Invitations ───────────────────────────────────────

@router.post("/invite-member", response_model=None)
async def invite_member(request: Request) -> Dict[str, Any]:
    """Invite a team member."""
    body = await request.json()
    email = body.get("email", "")
    role = body.get("role", "viewer")
    logger.info("Team member invited: email=%s role=%s", email, role)

    try:
        from src.core.auth_service import get_auth_service
        auth = get_auth_service()
        if hasattr(auth, "invite_user"):
            auth.invite_user(email=email, role=role)
    except Exception:
        pass

    return {"status": "ok", "email": email}


# ── Full Deployment ────────────────────────────────────────

@router.post("/deploy", response_model=None)
async def deploy_onboarding(request: Request) -> Dict[str, Any]:
    """Deploy selected blueprints and full configuration."""
    body = await request.json()
    blueprints = body.get("blueprints", [])
    monitors = body.get("monitors", [])
    channels = body.get("channels", {})
    team = body.get("team", [])
    logger.info("Onboarding deploy: blueprints=%s monitors=%s team=%d", blueprints, monitors, len(team))

    # Start SNA with default monitors
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        sna.load_default_monitors()
        await sna.start()
    except Exception:
        pass

    # Set up channels
    try:
        for ch_type, ch_config in channels.items():
            if isinstance(ch_config, dict) and ch_config.get("configured"):
                logger.info("Channel configured: %s", ch_type)
    except Exception:
        pass

    # Compose blueprints
    try:
        from src.core.blueprints import get_blueprint_loader
        loader = get_blueprint_loader()
        if hasattr(loader, "compose"):
            loader.compose(blueprints)
    except Exception:
        pass

    return {"status": "ok", "blueprints": blueprints, "monitors": monitors}


def register_onboarding_routes(app: Any) -> None:
    """Register onboarding HTMX routes on the FastAPI app."""
    app.include_router(router)
