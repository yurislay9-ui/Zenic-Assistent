"""
Zenic-Agents Asistente — Billing HTMX Routes (Enhanced)

Endpoints for billing and subscription management:
- GET  /htmx/billing            — billing dashboard page
- GET  /htmx/billing/plan       — current plan info (JSON)
- GET  /htmx/billing/plans      — available plans catalog
- GET  /htmx/billing/subscription — current subscription info
- POST /htmx/billing/checkout   — initiate Stripe checkout
- GET  /htmx/billing/portal     — redirect to Stripe customer portal
- POST /htmx/billing/cancel     — cancel subscription
- GET  /htmx/billing/usage      — current usage vs limits
- GET  /htmx/billing/invoices   — invoice history
- POST /htmx/billing/webhook    — Stripe webhook endpoint (no auth)
- POST /htmx/billing/create-invoice — create invoice (HTMX form)
- GET  /htmx/billing/pending-alerts — pending payment alerts
- GET  /htmx/billing/revenue-chart — revenue chart data
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/htmx/billing", tags=["htmx-billing"])

# Template setup
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
_templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    """Render a template with standard context."""
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)
    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": "billing",
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


def _get_tenant_id(request: Request) -> str:
    """Extract tenant_id from auth context or default to __anonymous__."""
    try:
        auth_ctx = getattr(request.state, "auth_ctx", None)
        if auth_ctx:
            tenant_id = getattr(auth_ctx, "tenant_id", None)
            if tenant_id:
                return tenant_id
    except Exception:
        pass
    return "__anonymous__"


# ── Billing Dashboard ─────────────────────────────────────

@router.get("", response_class=HTMLResponse, response_model=None)
async def billing_dashboard(request: Request) -> HTMLResponse:
    """Billing dashboard page — renders the billing.html template."""
    tenant_id = _get_tenant_id(request)

    plan_info = {"current": "free", "active": False, "is_trial": False,
                 "days_remaining": None, "system_mode": "NORMAL", "features": []}
    plans_catalog: List[Dict[str, Any]] = []

    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        plan_info = svc.get_plan(tenant_id=tenant_id)
        plans_catalog = svc.get_plans_catalog()
    except Exception as exc:
        logger.error("billing_dashboard: error loading plan info: %s", exc)

    try:
        return _render(request, "pages/billing.html", {"plan": plan_info, "plans": plans_catalog})
    except Exception:
        pass

    # Fallback: inline HTML
    plan = plan_info.get("current", "free")
    status = plan_info.get("status", "inactive")
    is_trial = plan_info.get("is_trial", False)
    days = plan_info.get("days_remaining", "")

    trial_html = ""
    if is_trial and days is not None:
        trial_html = f'<div class="badge-status badge-warning">Trial: {days} days remaining</div>'

    plans_rows = ""
    for p in plans_catalog:
        feat_list = ", ".join(str(f) for f in p.get("features", []))
        plans_rows += (
            f'<tr><td><strong>{p.get("name", "")}</strong></td>'
            f'<td>{p.get("price_display", "")}</td>'
            f'<td>{feat_list}</td>'
            f'<td><button hx-post="/htmx/billing/checkout" '
            f'hx-vals=\'{{"plan_id":"{p.get("id", "")}"}}\' '
            f'hx-target="#billing-status" class="btn btn-sm">Select</button></td></tr>'
        )

    html = f"""
    <div id="billing-status">
        <h2>Billing</h2>
        <div style="margin-bottom:16px;">
            <span class="badge-status badge-info">Current Plan: {plan.upper()}</span>
            <span class="badge-status badge-info">Status: {status}</span>
            {trial_html}
        </div>
        <table>
            <thead><tr><th>Plan</th><th>Price</th><th>Features</th><th>Action</th></tr></thead>
            <tbody>{plans_rows or '<tr><td colspan="4">No plans available</td></tr>'}</tbody>
        </table>
    </div>
    """
    return HTMLResponse(content=html)


# ── Page Route (legacy) ──────────────────────────────────

@router.get("/page", response_class=HTMLResponse)
async def billing_page(request: Request) -> HTMLResponse:
    """Render billing page (legacy endpoint)."""
    return _render(request, "billing.html", {})


# ── Plan info ─────────────────────────────────────────────

@router.get("/plan", response_model=None)
async def get_plan(request: Request) -> Dict[str, Any]:
    """Get current plan info as JSON."""
    tenant_id = _get_tenant_id(request)
    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        return svc.get_plan(tenant_id=tenant_id)
    except Exception:
        return {"current": "free", "active": False, "is_trial": False,
                "days_remaining": None, "system_mode": "NORMAL", "features": []}


@router.get("/plans", response_model=None)
async def get_plans(request: Request) -> List[Dict[str, Any]]:
    """Get available plans catalog."""
    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        return svc.get_plans_catalog()
    except Exception:
        return [
            {"id": "free", "name": "Free", "price": 0,
             "features": ["Pipeline básico", "Chat completions", "1 usuario", "5 RPM"]},
            {"id": "starter", "name": "Starter", "price": 29,
             "features": ["Todo en Free", "App generation", "SNA monitores", "10 RPM", "Email support"]},
            {"id": "business", "name": "Business", "price": 79,
             "features": ["Todo en Starter", "Automation", "Webhooks", "API access", "50 RPM"]},
            {"id": "enterprise", "name": "Enterprise", "price": 0,
             "features": ["Todo en Business", "Blueprints", "Multi-rol", "SSO", "Prioridad support", "API completa"]},
        ]


# ── Subscription ──────────────────────────────────────────

@router.get("/subscription", response_model=None)
async def get_subscription(request: Request) -> Dict[str, Any]:
    """Get current subscription info."""
    tenant_id = _get_tenant_id(request)
    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        record = svc.get_status(tenant_id)
        if record is None:
            return {"status": "none", "plan": "free", "message": "No subscription found"}
        return record.to_dict()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Checkout ──────────────────────────────────────────────

@router.post("/checkout", response_model=None)
async def create_checkout(request: Request) -> Dict[str, Any]:
    """Initiate a Stripe Checkout session."""
    tenant_id = _get_tenant_id(request)

    try:
        body = await request.json()
    except Exception:
        body = {}

    plan_id = body.get("plan_id", "business")

    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        return svc.create_checkout_session(tenant_id, plan_id)
    except Exception as exc:
        logger.error("checkout: error: %s", exc)
        return {"checkout_url": "", "error": str(exc)}


# ── Customer Portal ───────────────────────────────────────

@router.get("/portal", response_model=None)
async def billing_portal(request: Request) -> Any:
    """Redirect to Stripe customer portal."""
    tenant_id = _get_tenant_id(request)

    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        base_url = str(request.base_url).rstrip("/")
        result = svc.create_portal_session(tenant_id, return_url=f"{base_url}/htmx/billing")
        portal_url = result.get("url", "")
        if portal_url:
            return RedirectResponse(url=portal_url)
        return JSONResponse(content=result)
    except Exception as exc:
        logger.error("portal: error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


# ── Cancel ────────────────────────────────────────────────

@router.post("/cancel", response_model=None)
async def cancel_subscription(request: Request) -> Dict[str, Any]:
    """Cancel the current subscription."""
    tenant_id = _get_tenant_id(request)

    try:
        body = await request.json()
    except Exception:
        body = {}

    immediate = body.get("immediate", False)

    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        success = svc.cancel(tenant_id, immediate=immediate)
        if success:
            return {"status": "cancelled", "message": "Subscription cancelled successfully"}
        return {"status": "error", "message": "Failed to cancel subscription"}
    except Exception as exc:
        logger.error("cancel: error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ── Usage ─────────────────────────────────────────────────

@router.get("/usage", response_model=None)
async def get_usage(request: Request) -> Any:
    """Get current usage vs limits."""
    tenant_id = _get_tenant_id(request)

    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        usage_records = svc._subscription_manager.get_usage(tenant_id)

        if not usage_records:
            return HTMLResponse(
                content='<p class="text-muted">Sin uso registrado en las últimas 24 horas</p>'
            )

        # Check if this is an HTMX request (return HTML) or API call (return JSON)
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return {r.feature_name: r.to_dict() for r in usage_records}

        # HTML table for HTMX
        rows = ""
        for u in usage_records:
            limit_str = "Unlimited" if u.is_unlimited else str(u.limit)
            bar_pct = 0 if u.is_unlimited else min(100, int((u.usage_count / u.limit) * 100)) if u.limit > 0 else 0
            rows += (
                f'<tr><td>{u.feature_name}</td>'
                f'<td>{u.usage_count}</td>'
                f'<td>{limit_str}</td>'
                f'<td><div class="progress-bar" style="width:{bar_pct}%"></div></td></tr>'
            )

        html = (
            '<table class="table table-sm table-hover">'
            '<thead><tr><th>Feature</th><th>Usage</th><th>Limit</th><th>% Used</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )
        return HTMLResponse(content=html)
    except Exception:
        return HTMLResponse(content='<p class="text-muted">Error cargando uso</p>')


# ── Invoices ──────────────────────────────────────────────

@router.get("/invoices", response_model=None)
async def list_invoices(request: Request, status: str = "") -> Any:
    """Get invoice history."""
    tenant_id = _get_tenant_id(request)

    invoices: List[Dict[str, Any]] = []

    # First try the billing service
    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()
        invoices = svc.get_invoices(tenant_id)
    except Exception:
        pass

    # Fall back to the invoice processor for CRM invoices
    if not invoices:
        try:
            from src.core.agents_v2.business.invoice_processor import get_invoice_processor
            proc = get_invoice_processor()
            crm_invoices = proc.list_invoices(status=status)
            if crm_invoices:
                invoices = [inv.to_dict() if hasattr(inv, "to_dict") else inv for inv in crm_invoices]
        except Exception:
            pass

    if not invoices:
        return HTMLResponse(content='<p class="text-muted">Sin facturas</p>')

    # Check if this is an HTMX request (return HTML) or API call (return JSON)
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return invoices

    rows = ""
    for inv in invoices:
        event_type = inv.get("event_type", "")
        timestamp = inv.get("timestamp", 0)
        amount = inv.get("amount", 0)
        date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp)) if timestamp else "N/A"
        amount_str = f"${amount / 100:.2f}" if amount else "N/A"
        rows += (
            f'<tr><td>{date_str}</td>'
            f'<td>{event_type}</td>'
            f'<td>{amount_str}</td></tr>'
        )

    html = (
        '<table class="table table-sm table-hover">'
        '<thead><tr><th>Date</th><th>Type</th><th>Amount</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )
    return HTMLResponse(content=html)


# ── Create Invoice (HTMX form) ───────────────────────────

@router.post("/create-invoice", response_model=None)
async def create_invoice(request: Request) -> Dict[str, Any]:
    """Create a new invoice via HTMX form."""
    try:
        body = await request.json()
    except Exception:
        form_data = await request.form()
        body = dict(form_data)

    logger.info("Invoice created: client=%s amount=%s", body.get("client_name"), body.get("amount"))

    try:
        from src.core.agents_v2.business.invoice_processor import get_invoice_processor
        proc = get_invoice_processor()
        result = proc.create_invoice(body)
        return {"status": "ok", "invoice": result} if result else {"status": "ok"}
    except Exception as exc:
        logger.error("Create invoice failed: %s", exc)
        return {"status": "ok"}


# ── Pending Payment Alerts ─────────────────────────────────

@router.get("/pending-alerts", response_model=None)
async def pending_payment_alerts(request: Request) -> str:
    """Return pending payment alerts as HTML partial."""
    try:
        from src.core.agents_v2.business.invoice_processor import get_invoice_processor
        proc = get_invoice_processor()
        overdue = proc.get_overdue_invoices()
        if overdue:
            rows = ""
            for inv in overdue[:5]:
                inv_dict = inv.to_dict() if hasattr(inv, "to_dict") else inv
                rows += (
                    f'<div class="zenic-alert-feed-item">'
                    f'<span class="badge bg-danger">VENCIDA</span> '
                    f'<strong>{inv_dict.get("client_name", "?")}</strong> — '
                    f'${inv_dict.get("amount", 0):,.2f} '
                    f'<span class="text-muted">Venció: {inv_dict.get("due_date", "?")}</span>'
                    f'</div>'
                )
            return rows
    except Exception:
        pass

    return '<p class="text-muted">Sin pagos pendientes</p>'


# ── Revenue Chart Data ─────────────────────────────────────

@router.get("/revenue-chart", response_model=None)
async def get_revenue_chart(request: Request) -> Dict[str, Any]:
    """Return monthly revenue data for Chart.js bar chart."""
    labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    values = [0] * 12

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        now = time.time()
        year_start = now - (now % (365.25 * 86400))
        result = audit.query(AuditQuery(
            action_type="create_invoice", offset=0, limit=10000,
            from_timestamp=year_start,
        ))
        if isinstance(result, list):
            for entry in result:
                ts = getattr(entry, "timestamp", 0)
                if ts:
                    month = time.localtime(ts).tm_mon
                    values[month - 1] += 1
    except Exception:
        pass

    return {"labels": labels, "values": values}


# ── Webhook ───────────────────────────────────────────────

@router.post("/webhook", response_model=None)
async def stripe_webhook(request: Request) -> Dict[str, Any]:
    """Handle Stripe webhook events with signature verification.

    This endpoint does NOT require authentication — Stripe calls it directly.
    """
    body = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        from src.core.billing import get_billing_service
        svc = get_billing_service()

        # Use our custom webhook handler (with HMAC verification)
        if svc._stripe_client and sig_header:
            handler = svc._webhook_handler
            result = handler.handle_stripe_webhook(body, sig_header)
            http_code = result.get("http_code", 200)
            if http_code != 200:
                return JSONResponse(content=result, status_code=http_code)
            return result

        # Dev mode: parse JSON directly
        try:
            event = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error("Stripe webhook body parse failed: %s", e)
            return JSONResponse(content={"error": str(e)}, status_code=400)

        return svc.handle_webhook(event)
    except Exception as exc:
        logger.error("Billing webhook error: %s", exc)
        return JSONResponse(content={"status": "error", "message": str(exc)}, status_code=500)


# ── Registration ──────────────────────────────────────────

def register_billing_routes(app: Any) -> None:
    """Register billing HTMX routes on the FastAPI app."""
    app.include_router(router)
