"""
Zenic-Agents Asistente — Dashboard HTMX Routes (Phase 7.2 + Enhanced)

HTMX endpoints for the executive dashboard:
- Page rendering (TemplateResponse)
- KPI data as HTML fragment
- Actions chart data (Chart.js format)
- Category chart data (Chart.js format)
- Recent activity table
- Alert feed from SNA
- ROI metrics (Phase D2)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["htmx-dashboard"])


# ── Template Setup ─────────────────────────────────────────

import os
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
try:
    from fastapi.templating import Jinja2Templates
    _templates = Jinja2Templates(directory=_templates_dir)
except Exception:
    _templates = None


def _render(request: Request, template_name: str, context: Dict[str, Any]) -> HTMLResponse:
    """Render a template with standard context."""
    if _templates is None:
        return HTMLResponse(content=f"<h1>Template '{template_name}' not found</h1>", status_code=500)

    ctx = {
        "request": request,
        "current_user": {"username": "Admin", "role": "admin"},
        "active_page": template_name.replace(".html", ""),
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


# ── Page Routes ────────────────────────────────────────────

@router.get("/htmx/", response_class=HTMLResponse)
async def htmx_index(request: Request):
    """Redirect /htmx/ to dashboard."""
    return RedirectResponse(url="/htmx/dashboard")


@router.get("/htmx/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Render the executive dashboard page."""
    return _render(request, "dashboard.html", {})


# ── KPI Data Endpoint ──────────────────────────────────────

@router.get("/htmx/dashboard/kpis", response_model=None)
async def get_kpis(request: Request) -> str:
    """Return KPI cards as HTML fragment for HTMX swap."""
    total_actions = 0
    success_rate = 0.0
    active_monitors = 0
    pending_approvals = 0

    # Total actions from audit
    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        now = time.time()
        today_start = now - (now % 86400)
        result = audit.query(AuditQuery(offset=0, limit=0, from_timestamp=today_start))
        total_actions = len(result) if isinstance(result, list) else 0
    except Exception:
        pass

    # Success rate from audit
    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        result = audit.query(AuditQuery(offset=0, limit=1000))
        if isinstance(result, list) and len(result) > 0:
            allowed = sum(1 for e in result if getattr(e, "verdict", "") == "ALLOW")
            success_rate = (allowed / len(result)) * 100
    except Exception:
        pass

    # Active monitors from SNA
    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        stats = sna.detailed_stats
        active_monitors = stats.get("scheduler", {}).get("active_monitors", 0)
    except Exception:
        pass

    # Pending approvals from approval system
    try:
        from src.core.approval.chain import ApprovalChain
        chain = ApprovalChain()
        pending = chain.get_pending()
        pending_approvals = len(pending) if isinstance(pending, list) else 0
    except Exception:
        pass

    return f'''
    <div class="col-12 col-md-6 col-xl-3">
      <div class="card zenic-kpi h-100">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <p class="text-muted small mb-1">Total Acciones</p>
              <h3 class="mb-0">{total_actions}</h3>
            </div>
            <div class="zenic-kpi-icon bg-primary bg-opacity-10 text-primary"><i class="bi bi-lightning-charge"></i></div>
          </div>
        </div>
      </div>
    </div>
    <div class="col-12 col-md-6 col-xl-3">
      <div class="card zenic-kpi h-100">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <p class="text-muted small mb-1">Tasa de Éxito</p>
              <h3 class="mb-0">{success_rate:.1f}%</h3>
            </div>
            <div class="zenic-kpi-icon bg-success bg-opacity-10 text-success"><i class="bi bi-check-circle"></i></div>
          </div>
        </div>
      </div>
    </div>
    <div class="col-12 col-md-6 col-xl-3">
      <div class="card zenic-kpi h-100">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <p class="text-muted small mb-1">Monitores Activos</p>
              <h3 class="mb-0">{active_monitors}</h3>
            </div>
            <div class="zenic-kpi-icon bg-warning bg-opacity-10 text-warning"><i class="bi bi-activity"></i></div>
          </div>
        </div>
      </div>
    </div>
    <div class="col-12 col-md-6 col-xl-3">
      <div class="card zenic-kpi h-100">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <p class="text-muted small mb-1">Aprobaciones Pendientes</p>
              <h3 class="mb-0">{pending_approvals}</h3>
            </div>
            <div class="zenic-kpi-icon bg-danger bg-opacity-10 text-danger"><i class="bi bi-hourglass-split"></i></div>
          </div>
        </div>
      </div>
    </div>
    '''


# ── Chart Data Endpoints ───────────────────────────────────

@router.get("/htmx/dashboard/actions-chart", response_model=None)
async def get_actions_chart(request: Request) -> Dict[str, Any]:
    """Return 7-day actions data for Chart.js line chart."""
    labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    values = [0, 0, 0, 0, 0, 0, 0]

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        now = time.time()
        for i in range(7):
            day_start = now - ((6 - i) * 86400)
            day_end = day_start + 86400
            result = audit.query(AuditQuery(
                offset=0, limit=10000,
                from_timestamp=day_start, to_timestamp=day_end,
            ))
            values[i] = len(result) if isinstance(result, list) else 0
    except Exception:
        pass

    return {"labels": labels, "values": values}


@router.get("/htmx/dashboard/category-chart", response_model=None)
async def get_category_chart(request: Request) -> Dict[str, Any]:
    """Return actions by category for Chart.js pie chart."""
    labels = ["Email", "HTTP", "DB", "File", "Notify", "Schedule", "Webhook", "Transform"]
    values = [0, 0, 0, 0, 0, 0, 0, 0]
    type_map = {
        "email": 0, "http": 1, "database": 2, "file": 3,
        "notification": 4, "schedule": 5, "webhook": 6, "transform": 7,
    }

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        cutoff = time.time() - (7 * 86400)
        result = audit.query(AuditQuery(offset=0, limit=10000, from_timestamp=cutoff))
        if isinstance(result, list):
            for entry in result:
                idx = type_map.get(getattr(entry, "action_type", "").lower(), -1)
                if 0 <= idx < len(values):
                    values[idx] += 1
    except Exception:
        pass

    return {"labels": labels, "values": values}


@router.get("/htmx/dashboard/executor-chart", response_model=None)
async def get_executor_chart(request: Request) -> Dict[str, Any]:
    """Return executor action distribution for Chart.js bar chart."""
    labels = ["Email", "HTTP", "DB", "File", "Notify", "Schedule", "Webhook", "Transform"]
    values = [0, 0, 0, 0, 0, 0, 0, 0]
    type_map = {
        "email": 0, "http": 1, "database": 2, "file": 3,
        "notification": 4, "schedule": 5, "webhook": 6, "transform": 7,
    }

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        cutoff = time.time() - (7 * 86400)
        result = audit.query(AuditQuery(offset=0, limit=10000, from_timestamp=cutoff))
        if isinstance(result, list):
            for entry in result:
                idx = type_map.get(getattr(entry, "action_type", "").lower(), -1)
                if 0 <= idx < len(values):
                    values[idx] += 1
    except Exception:
        pass

    return {"labels": labels, "values": values}


# ── Metrics JSON (for Alpine.js) ───────────────────────────

@router.get("/htmx/dashboard/metrics", response_model=None)
async def get_metrics(request: Request) -> Dict[str, Any]:
    """Return dashboard metrics as JSON for Alpine.js."""
    metrics: Dict[str, Any] = {
        "sales_today": "0",
        "sales_change": 0.0,
        "pending_invoices": 0,
        "active_alerts": 0,
        "system_mode": "NORMAL",
    }

    try:
        from src.core.sna import get_sna_engine
        sna = get_sna_engine()
        stats = sna.detailed_stats
        metrics["active_alerts"] = stats.get("alert_manager", {}).get("active_alerts", 0)
    except Exception:
        pass

    try:
        from src.core.degraded_mode import get_degraded_mode_manager
        dm = get_degraded_mode_manager()
        metrics["system_mode"] = dm.get_current_mode().value.upper()
    except Exception:
        pass

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        now = time.time()
        today_start = now - (now % 86400)
        result = audit.query(AuditQuery(offset=0, limit=0, from_timestamp=today_start))
        metrics["sales_today"] = str(len(result)) if isinstance(result, list) else "0"
    except Exception:
        pass

    try:
        from src.core.roi import get_roi_dashboard_data
        roi_dash = get_roi_dashboard_data()
        roi_metrics = roi_dash.get_metrics()
        metrics["hours_saved"] = roi_metrics.get("hours_saved", 0)
        metrics["errors_avoided"] = roi_metrics.get("errors_avoided", 0)
        metrics["revenue_recovered"] = roi_metrics.get("revenue_recovered", 0.0)
        metrics["roi_percent"] = roi_metrics.get("roi_percent", 0.0)
    except Exception:
        pass

    return metrics


# ── Sales Chart (legacy compat) ────────────────────────────

@router.get("/htmx/dashboard/sales-chart", response_model=None)
async def get_sales_chart(request: Request) -> Dict[str, Any]:
    """Return 7-day sales data for Chart.js."""
    labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    values = [0, 0, 0, 0, 0, 0, 0]

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        now = time.time()
        for i in range(7):
            day_start = now - ((6 - i) * 86400)
            day_end = day_start + 86400
            result = audit.query(AuditQuery(
                action_type="create_invoice", offset=0, limit=1000,
                from_timestamp=day_start, to_timestamp=day_end,
            ))
            values[i] = len(result) if isinstance(result, list) else 0
    except Exception:
        pass

    return {"labels": labels, "values": values}


# ── Recent Activity ────────────────────────────────────────

@router.get("/htmx/dashboard/recent-activity", response_model=None)
async def get_recent_activity(request: Request) -> str:
    """Return recent activity as HTML table partial (last 20 actions)."""
    rows_html = '<tr><td colspan="7" class="text-center text-muted py-4">Sin actividad reciente</td></tr>'

    try:
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery
        audit = get_default_audit_logger()
        result = audit.query(AuditQuery(offset=0, limit=20))
        if isinstance(result, list) and result:
            lines = []
            for e in result:
                ts = getattr(e, "timestamp", 0)
                ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--"
                action = getattr(e, "action_type", "--")
                op = getattr(e, "operation", "--")
                verdict = getattr(e, "verdict", "--")
                risk = getattr(e, "risk_score", 0)
                vclass = {"ALLOW": "bg-success", "DENY": "bg-danger",
                          "CONFIRM": "bg-info", "RATE_LIMITED": "bg-warning text-dark"}.get(verdict, "bg-secondary")
                risk_class = "text-danger fw-bold" if risk > 0.7 else ""
                lines.append(
                    f'<tr>'
                    f'<td class="font-monospace small">{ts_str}</td>'
                    f'<td>{action}</td>'
                    f'<td>{op}</td>'
                    f'<td><span class="badge {vclass}">{verdict}</span></td>'
                    f'<td class="{risk_class}">{risk*100:.0f}%</td>'
                    f'</tr>'
                )
            rows_html = "".join(lines)
    except Exception:
        pass

    return (
        '<table class="table table-hover mb-0">'
        '<thead><tr><th>Hora</th><th>Acción</th><th>Operación</th><th>Veredicto</th><th>Risk</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
    )


# ── SNA Alerts ─────────────────────────────────────────────

@router.get("/htmx/dashboard/alerts", response_model=None)
async def get_sna_alerts(request: Request) -> str:
    """Return SNA alerts as HTML feed partial."""
    items_html = '<p class="text-muted">Sin alertas activas</p>'

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
                sev_class = {"warning": "bg-warning text-dark", "critical": "bg-danger"}.get(sev, "bg-info")
                lines.append(
                    f'<div class="zenic-alert-feed-item">'
                    f'<span class="badge {sev_class}">{sev.upper()}</span> '
                    f'<span class="small">{detail}</span></div>'
                )
            items_html = "".join(lines)
    except Exception:
        pass

    return items_html


# ── ROI Metrics (Phase D2) ─────────────────────────────────

@router.get("/htmx/dashboard/roi-metrics", response_model=None)
async def get_roi_metrics(request: Request) -> Dict[str, Any]:
    """Return ROI metrics as JSON for Alpine.js widgets."""
    try:
        from src.core.roi import get_roi_dashboard_data
        dashboard = get_roi_dashboard_data()
        return dashboard.get_metrics()
    except Exception:
        return {
            "hours_saved": 0, "errors_avoided": 0,
            "revenue_recovered": 0.0, "tasks_automated": 0,
            "roi_percent": 0.0, "net_value": 0.0,
        }


@router.get("/htmx/dashboard/roi-trend/{metric}", response_model=None)
async def get_roi_trend(request: Request, metric: str) -> Dict[str, Any]:
    """Return ROI trend data for Chart.js."""
    try:
        from src.core.roi import get_roi_dashboard_data
        dashboard = get_roi_dashboard_data()
        points = dashboard.get_trend(metric, days=30)
        return {
            "labels": [p.timestamp[:10] for p in points],
            "values": [p.value for p in points],
        }
    except Exception:
        return {"labels": [], "values": []}


@router.get("/htmx/dashboard/roi-impact-table", response_model=None)
async def get_roi_impact_table(request: Request) -> str:
    """Return top urgent impacts as HTML table partial."""
    rows_html = '<tr><td colspan="4" class="text-center text-muted py-3">Sin datos de impacto</td></tr>'
    try:
        from src.core.roi import get_impact_scorer
        scorer = get_impact_scorer()
        impacts = scorer.get_top_impacts(limit=5)
        if impacts:
            lines = []
            for imp in impacts:
                loss = getattr(imp, 'estimated_loss_if_no_action', 0)
                gain = getattr(imp, 'estimated_gain_if_action', 0)
                urgency = getattr(imp, 'urgency_hours', 0)
                lines.append(
                    f'<tr><td>{getattr(imp, "impact_type", "?")}</td>'
                    f'<td>${loss:,.0f}</td><td>${gain:,.0f}</td>'
                    f'<td>{urgency:.0f}h</td></tr>'
                )
            rows_html = "".join(lines)
    except Exception:
        pass
    return (
        '<table class="table table-sm table-hover">'
        '<thead><tr><th>Tipo</th><th>Pérdida</th><th>Ganancia</th><th>Urgencia</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
    )


# ── Registration ───────────────────────────────────────────

def register_dashboard_routes(app: Any) -> None:
    """Register dashboard HTMX routes on the FastAPI app."""
    app.include_router(router)
