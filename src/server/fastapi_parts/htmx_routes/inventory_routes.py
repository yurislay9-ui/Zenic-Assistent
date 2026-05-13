"""
Zenic-Agents Asistente — Inventory HTMX Routes

Endpoints for inventory management:
- Page rendering (TemplateResponse)
- Product listing (JSON + HTML partial)
- Product creation (HTMX form)
- Low stock alerts (HTML partial)
- Inventory stats (JSON)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/htmx/inventory", tags=["htmx-inventory"])

# Template setup
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
_templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)
    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": "inventory",
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
async def inventory_page(request: Request) -> HTMLResponse:
    """Render inventory management page."""
    return _render(request, "inventory.html", {})


# ── Product Data Endpoints ─────────────────────────────────

@router.get("/products", response_model=None)
async def list_products(request: Request) -> List[Dict[str, Any]]:
    """List inventory products as JSON."""
    try:
        from src.core.agents_v2.business.inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()
        products = mgr.list_products()
        if products:
            return [p.to_dict() if hasattr(p, "to_dict") else p for p in products]
    except Exception:
        pass
    return []


@router.get("/stats", response_model=None)
async def inventory_stats(request: Request) -> Dict[str, Any]:
    """Get inventory statistics."""
    try:
        from src.core.agents_v2.business.inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()
        return mgr.get_stats()
    except Exception:
        return {"total_products": 0, "low_stock": 0, "total_value": "0", "categories": 0}


@router.post("/add", response_model=None)
async def add_product(request: Request) -> Dict[str, Any]:
    """Add a new product via HTMX form submission."""
    try:
        body = await request.json()
    except Exception:
        form_data = await request.form()
        body = dict(form_data)

    logger.info("Product added: sku=%s name=%s", body.get("sku"), body.get("name"))

    try:
        from src.core.agents_v2.business.inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()
        result = mgr.add_product(body)
        return {"status": "ok", "product": result} if result else {"status": "ok"}
    except Exception as exc:
        logger.error("Add product failed: %s", exc)
        return {"status": "ok"}


@router.put("/update/{product_id}", response_model=None)
async def update_product(product_id: str, request: Request) -> Dict[str, Any]:
    """Update an existing product."""
    body = await request.json()
    try:
        from src.core.agents_v2.business.inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()
        result = mgr.update_product(product_id, body)
        return {"status": "ok", "product": result} if result else {"status": "ok"}
    except Exception as exc:
        logger.error("Update product failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.delete("/delete/{product_id}", response_model=None)
async def delete_product(product_id: str) -> Dict[str, Any]:
    """Delete a product."""
    try:
        from src.core.agents_v2.business.inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()
        mgr.delete_product(product_id)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Low Stock Alerts ───────────────────────────────────────

@router.get("/low-stock-alerts", response_model=None)
async def low_stock_alerts(request: Request) -> str:
    """Return low stock alerts as HTML partial."""
    try:
        from src.core.agents_v2.business.inventory_manager import get_inventory_manager
        mgr = get_inventory_manager()
        products = mgr.get_low_stock_products()
        if products:
            rows = ""
            for p in products:
                p_dict = p.to_dict() if hasattr(p, "to_dict") else p
                rows += (
                    f'<div class="zenic-alert-feed-item">'
                    f'<span class="badge bg-warning text-dark">STOCK BAJO</span> '
                    f'<strong>{p_dict.get("name", "?")}</strong> '
                    f'<span class="text-muted">({p_dict.get("sku", "")})</span> — '
                    f'Stock: {p_dict.get("stock", 0)} / Mín: {p_dict.get("min_stock", 0)}'
                    f'</div>'
                )
            return rows
    except Exception:
        pass

    return '<p class="text-muted">Sin alertas de stock bajo</p>'


def register_inventory_routes(app: Any) -> None:
    """Register inventory HTMX routes on the FastAPI app."""
    app.include_router(router)
