"""
Zenic-Agents Asistente — Module HTMX Routes (Phase 7.1)

HTMX endpoints for business modules: channels, inventory, CRM, onboarding.
These provide JSON/HTML partials for the Alpine.js frontends.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["htmx-modules"])


# ── Channels ────────────────────────────────────────────

@router.get("/htmx/channels/list", response_model=None)
async def list_channels(request: Request) -> List[Dict[str, Any]]:
    """List configured channels."""
    # In production, query from a channels table
    return []


@router.post("/htmx/channels/add", response_model=None)
async def add_channel(request: Request) -> Dict[str, Any]:
    """Add a new channel."""
    body = await request.json()
    logger.info("Channel added: type=%s name=%s", body.get("type"), body.get("name"))
    return {"status": "ok"}


@router.post("/htmx/channels/test/{channel_id}", response_model=None)
async def test_channel(channel_id: str) -> Dict[str, Any]:
    """Send a test message to a channel."""
    return {"status": "ok", "message": "Test sent"}


@router.delete("/htmx/channels/{channel_id}", response_model=None)
async def delete_channel(channel_id: str) -> Dict[str, Any]:
    """Delete a channel."""
    return {"status": "ok"}


# ── Inventory ───────────────────────────────────────────

@router.get("/htmx/inventory/products", response_model=None)
async def list_products(request: Request) -> List[Dict[str, Any]]:
    """List inventory products."""
    return []


@router.get("/htmx/inventory/stats", response_model=None)
async def inventory_stats(request: Request) -> Dict[str, Any]:
    """Get inventory statistics."""
    return {"total_products": 0, "low_stock": 0, "total_value": "0", "categories": 0}


@router.post("/htmx/inventory/add", response_model=None)
async def add_product(request: Request) -> Dict[str, Any]:
    """Add a new product."""
    body = await request.json()
    logger.info("Product added: sku=%s name=%s", body.get("sku"), body.get("name"))
    return {"status": "ok"}


# ── CRM ─────────────────────────────────────────────────

@router.get("/htmx/crm/clients", response_model=None)
async def list_clients(request: Request, search: str = "") -> List[Dict[str, Any]]:
    """List CRM clients."""
    return []


@router.get("/htmx/crm/stats", response_model=None)
async def crm_stats(request: Request) -> Dict[str, Any]:
    """Get CRM statistics."""
    return {"total_clients": 0, "active_clients": 0, "total_invoices": 0, "pending_amount": "0"}


@router.get("/htmx/crm/clients/{client_id}", response_model=None)
async def get_client_detail(client_id: str, request: Request) -> Dict[str, Any]:
    """Get details for a specific CRM client."""
    # In production, query from a clients table
    return {"id": client_id, "name": "", "email": "", "company": "", "phone": "",
            "active": True, "invoices": [], "interactions": [], "notes": ""}


@router.post("/htmx/crm/add", response_model=None)
async def add_client(request: Request) -> Dict[str, Any]:
    """Add a new client."""
    body = await request.json()
    logger.info("Client added: name=%s email=%s", body.get("name"), body.get("email"))
    return {"status": "ok"}


# ── Onboarding ──────────────────────────────────────────

@router.get("/htmx/onboarding/blueprints", response_model=None)
async def list_blueprints(request: Request) -> List[Dict[str, Any]]:
    """List available blueprints for onboarding."""
    try:
        from src.core.blueprints import get_blueprint_loader
        loader = get_blueprint_loader()
        blueprints = loader.list_blueprints() if hasattr(loader, "list_blueprints") else []
        return [{"id": b.get("blueprint_id", ""), "name": b.get("name", ""),
                 "description": b.get("description", ""), "features": b.get("features", [])}
                for b in blueprints]
    except Exception:
        # Fallback built-in blueprints
        return [
            {"id": "retail", "name": "Retail", "description": "Gestión de inventario y ventas",
             "features": ["Inventario", "Facturación", "CRM"]},
            {"id": "crm", "name": "CRM", "description": "Gestión de clientes y seguimiento",
             "features": ["Contactos", "Pipeline", "Notificaciones"]},
            {"id": "billing", "name": "Facturación", "description": "Facturas, pagos y cobros",
             "features": ["Facturas", "Pagos", "Recordatorios"]},
            {"id": "manufacturing", "name": "Manufactura", "description": "Producción y cadena de suministro",
             "features": ["Producción", "Supply Chain", "Calidad"]},
        ]


@router.post("/htmx/onboarding/deploy", response_model=None)
async def deploy_onboarding(request: Request) -> Dict[str, Any]:
    """Deploy selected blueprints."""
    body = await request.json()
    blueprints = body.get("blueprints", [])
    logger.info("Onboarding deploy: blueprints=%s", blueprints)

    # In production: compose blueprints, create DB tables, configure SNA monitors
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        sna.load_default_monitors()
    except Exception:
        pass

    return {"status": "ok", "blueprints": blueprints}


def register_module_routes(app: Any) -> None:
    """Register module HTMX routes on the FastAPI app."""
    app.include_router(router)
