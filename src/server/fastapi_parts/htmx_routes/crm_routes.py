"""
Zenic-Agents Asistente — CRM HTMX Routes

Endpoints for CRM management:
- Page rendering (TemplateResponse)
- Client listing with search (JSON + HTML partial)
- Client creation (HTMX form)
- Client detail (JSON + HTML partial)
- CRM stats (JSON)
- Conversion metrics (HTML partial)
- Pipeline data (JSON)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/htmx/crm", tags=["htmx-crm"])

# Template setup
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
_templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)
    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": "crm",
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
async def crm_page(request: Request) -> HTMLResponse:
    """Render CRM page."""
    return _render(request, "crm.html", {})


# ── Client Data Endpoints ─────────────────────────────────

@router.get("/clients", response_model=None)
async def list_clients(request: Request, search: str = "") -> List[Dict[str, Any]]:
    """List CRM clients with optional search."""
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        clients = pipeline.list_clients(search=search)
        if clients:
            return [c.to_dict() if hasattr(c, "to_dict") else c for c in clients]
    except Exception:
        pass
    return []


@router.get("/stats", response_model=None)
async def crm_stats(request: Request) -> Dict[str, Any]:
    """Get CRM statistics."""
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        return pipeline.get_stats()
    except Exception:
        return {"total_clients": 0, "active_clients": 0, "total_invoices": 0, "pending_amount": "0"}


@router.get("/clients/{client_id}", response_model=None)
async def get_client_detail(client_id: str, request: Request) -> Dict[str, Any]:
    """Get details for a specific CRM client."""
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        client = pipeline.get_client(client_id)
        if client:
            return client.to_dict() if hasattr(client, "to_dict") else client
    except Exception:
        pass
    return {"id": client_id, "name": "", "email": "", "company": "", "phone": "",
            "active": True, "invoices": [], "interactions": [], "notes": ""}


@router.post("/add", response_model=None)
async def add_client(request: Request) -> Dict[str, Any]:
    """Add a new client via HTMX form."""
    try:
        body = await request.json()
    except Exception:
        form_data = await request.form()
        body = dict(form_data)

    logger.info("Client added: name=%s email=%s", body.get("name"), body.get("email"))

    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        result = pipeline.add_client(body)
        return {"status": "ok", "client": result} if result else {"status": "ok"}
    except Exception as exc:
        logger.error("Add client failed: %s", exc)
        return {"status": "ok"}


@router.put("/update/{client_id}", response_model=None)
async def update_client(client_id: str, request: Request) -> Dict[str, Any]:
    """Update an existing client."""
    body = await request.json()
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        result = pipeline.update_client(client_id, body)
        return {"status": "ok", "client": result} if result else {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.delete("/delete/{client_id}", response_model=None)
async def delete_client(client_id: str) -> Dict[str, Any]:
    """Delete a client."""
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        pipeline.delete_client(client_id)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Pipeline Data ──────────────────────────────────────────

@router.get("/pipeline", response_model=None)
async def get_pipeline(request: Request) -> Dict[str, Any]:
    """Get pipeline data (clients grouped by stage)."""
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        return pipeline.get_pipeline_view()
    except Exception:
        return {"lead": [], "prospect": [], "negotiation": [], "closed": []}


# ── Conversion Metrics ─────────────────────────────────────

@router.get("/metrics", response_model=None)
async def get_crm_metrics(request: Request) -> str:
    """Return CRM conversion metrics as HTML partial."""
    try:
        from src.core.agents_v2.business.crm_pipeline import get_crm_pipeline
        pipeline = get_crm_pipeline()
        metrics = pipeline.get_conversion_metrics()
        if metrics:
            return (
                '<div class="row g-3">'
                f'<div class="col-md-4"><div class="text-center"><h4>{metrics.get("lead_to_prospect", "0%")}</h4><p class="text-muted small">Lead → Prospecto</p></div></div>'
                f'<div class="col-md-4"><div class="text-center"><h4>{metrics.get("prospect_to_negotiation", "0%")}</h4><p class="text-muted small">Prospecto → Negociación</p></div></div>'
                f'<div class="col-md-4"><div class="text-center"><h4>{metrics.get("negotiation_to_closed", "0%")}</h4><p class="text-muted small">Negociación → Cerrado</p></div></div>'
                '</div>'
            )
    except Exception:
        pass

    return (
        '<div class="row g-3">'
        '<div class="col-md-4"><div class="text-center"><h4>—</h4><p class="text-muted small">Lead → Prospecto</p></div></div>'
        '<div class="col-md-4"><div class="text-center"><h4>—</h4><p class="text-muted small">Prospecto → Negociación</p></div></div>'
        '<div class="col-md-4"><div class="text-center"><h4>—</h4><p class="text-muted small">Negociación → Cerrado</p></div></div>'
        '</div>'
    )


def register_crm_routes(app: Any) -> None:
    """Register CRM HTMX routes on the FastAPI app."""
    app.include_router(router)
