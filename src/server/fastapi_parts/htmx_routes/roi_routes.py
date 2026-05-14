"""
Zenic-Agents — ROI Dashboard HTMX Routes (Phase D2)

FastAPI HTMX endpoints for the ROI dashboard.  Returns metrics,
widget configurations, trend data (Chart.js format), impact tables,
cost/value breakdowns, period comparisons, and JSON data export.
All routes lazy-load ROIDashboardData and degrade gracefully on errors.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/htmx/roi", tags=["htmx-roi"])


# ── Lazy loader ──────────────────────────────────────────

_dashboard_data: Any = None


def _get_dashboard() -> Any:
    """Lazy-load the ROIDashboardData singleton."""
    global _dashboard_data
    if _dashboard_data is None:
        try:
            from src.core.roi.dashboard_data import get_roi_dashboard_data
            _dashboard_data = get_roi_dashboard_data()
        except Exception as exc:
            logger.error("roi_routes: ROIDashboardData unavailable: %s", exc)
    return _dashboard_data


# ── Routes ───────────────────────────────────────────────


@router.get("/metrics", response_model=None)
async def get_metrics(request: Request) -> Dict[str, Any]:
    """Return ROI metrics as JSON for Alpine.js."""
    try:
        dashboard = _get_dashboard()
        if dashboard is None:
            return _empty_metrics()
        return dashboard.get_metrics()
    except Exception as exc:
        logger.error("roi_routes: /metrics failed: %s", exc)
        return _empty_metrics()


@router.get("/widgets", response_model=None)
async def get_widgets(request: Request) -> List[Dict[str, Any]]:
    """Return widget configuration as JSON."""
    try:
        dashboard = _get_dashboard()
        if dashboard is None:
            return []
        widgets = dashboard.get_widgets()
        return [w.to_dict() if hasattr(w, "to_dict") else w for w in widgets]
    except Exception as exc:
        logger.error("roi_routes: /widgets failed: %s", exc)
        return []


@router.get("/trend/{metric}", response_model=None)
async def get_trend(request: Request, metric: str) -> Dict[str, Any]:
    """Return trend data for a specific metric in Chart.js format.

    Returns ``{"labels": [...], "values": [...]}``.
    """
    try:
        dashboard = _get_dashboard()
        if dashboard is None:
            return {"labels": [], "values": []}
        days = int(request.query_params.get("days", "30"))
        points = dashboard.get_trend(metric, days=days)
        labels = [p.timestamp for p in points]
        values = [p.value for p in points]
        return {"labels": labels, "values": values}
    except Exception as exc:
        logger.error("roi_routes: /trend/%s failed: %s", metric, exc)
        return {"labels": [], "values": []}


@router.get("/impact-table", response_model=None)
async def get_impact_table(request: Request) -> str:
    """Return top urgent impacts as an HTML table partial."""
    try:
        dashboard = _get_dashboard()
        if dashboard is None:
            return '<p class="text-muted text-sm">Impact data unavailable</p>'

        # Lazy-load impact scorer directly
        try:
            from src.core.roi.impact_scorer import get_impact_scorer
            scorer = get_impact_scorer()
            impacts = scorer.get_urgent_actions(max_urgency_hours=72)
        except Exception:
            impacts = []

        if not impacts:
            return '<p class="text-muted text-sm">No urgent impacts found</p>'

        rows_html = ""
        for imp in impacts[:10]:
            imp_dict = imp.to_dict() if hasattr(imp, "to_dict") else imp
            rows_html += (
                f'<tr>'
                f'<td>{imp_dict.get("impact_type", "")}</td>'
                f'<td>${imp_dict.get("estimated_loss_if_no_action", 0):,.2f}</td>'
                f'<td>${imp_dict.get("estimated_gain_if_action", 0):,.2f}</td>'
                f'<td>{imp_dict.get("urgency_hours", 0):.1f}h</td>'
                f'<td>{imp_dict.get("impact_score", 0):.2f}</td>'
                f'</tr>'
            )

        return (
            '<table class="table table-sm table-striped">'
            '<thead><tr>'
            '<th>Type</th><th>Potential Loss</th>'
            '<th>Potential Gain</th><th>Urgency</th><th>Score</th>'
            '</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            '</table>'
        )
    except Exception as exc:
        logger.error("roi_routes: /impact-table failed: %s", exc)
        return '<p class="text-muted text-sm">Error loading impact data</p>'


@router.get("/cost-breakdown", response_model=None)
async def get_cost_breakdown(request: Request) -> str:
    """Return cost breakdown as an HTML partial."""
    try:
        from src.core.roi.cost_accumulator import get_cost_accumulator
        acc = get_cost_accumulator()
        breakdown = acc.get_cost_breakdown()
    except Exception:
        breakdown = {}

    if not breakdown:
        return '<p class="text-muted text-sm">No cost data available</p>'

    rows_html = ""
    for category, total in sorted(breakdown.items(), key=lambda x: -x[1]):
        rows_html += (
            f'<tr>'
            f'<td>{category}</td>'
            f'<td>${total:,.2f}</td>'
            f'</tr>'
        )

    return (
        '<table class="table table-sm table-striped">'
        '<thead><tr><th>Category</th><th>Total Cost</th></tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
    )


@router.get("/value-breakdown", response_model=None)
async def get_value_breakdown(request: Request) -> str:
    """Return value breakdown as an HTML partial."""
    try:
        from src.core.roi.value_tracker import get_value_tracker
        vt = get_value_tracker()
        breakdown = vt.get_value_breakdown()
    except Exception:
        breakdown = {}

    if not breakdown:
        return '<p class="text-muted text-sm">No value data available</p>'

    rows_html = ""
    for category, total in sorted(breakdown.items(), key=lambda x: -x[1]):
        rows_html += (
            f'<tr>'
            f'<td>{category}</td>'
            f'<td>${total:,.2f}</td>'
            f'</tr>'
        )

    return (
        '<table class="table table-sm table-striped">'
        '<thead><tr><th>Category</th><th>Total Value</th></tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
    )


@router.get("/comparison", response_model=None)
async def get_comparison(request: Request) -> Dict[str, Any]:
    """Return period comparison data as JSON."""
    try:
        dashboard = _get_dashboard()
        if dashboard is None:
            return _empty_comparison()

        period_a = int(request.query_params.get("period_a", "7"))
        period_b = int(request.query_params.get("period_b", "7"))
        return dashboard.get_comparison(period_a, period_b)
    except Exception as exc:
        logger.error("roi_routes: /comparison failed: %s", exc)
        return _empty_comparison()


@router.get("/export", response_model=None)
async def export_data(request: Request) -> Response:
    """Export all ROI data as a JSON file download."""
    try:
        dashboard = _get_dashboard()
        if dashboard is None:
            return JSONResponse(
                content={"error": "Dashboard data unavailable"},
                status_code=503,
            )
        data = dashboard.export_data(format="json")
        return Response(
            content=data,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=roi_dashboard_export.json",
            },
        )
    except Exception as exc:
        logger.error("roi_routes: /export failed: %s", exc)
        return JSONResponse(
            content={"error": str(exc)},
            status_code=500,
        )


# ── Registration ─────────────────────────────────────────


def register_roi_routes(app: Any) -> None:
    """Register the ROI HTMX router on the FastAPI app."""
    app.include_router(router)


# ── Fallback data ────────────────────────────────────────


def _empty_metrics() -> Dict[str, Any]:
    """Return zeroed-out metrics for graceful degradation."""
    return {
        "hours_saved": 0.0,
        "errors_avoided": 0,
        "revenue_recovered": 0.0,
        "tasks_automated": 0,
        "roi_percent": 0.0,
        "net_value": 0.0,
        "total_cost": 0.0,
        "total_value": 0.0,
        "cost_breakdown": {},
        "value_breakdown": {},
        "impact_summary": {},
    }


def _empty_comparison() -> Dict[str, Any]:
    """Return zeroed-out comparison for graceful degradation."""
    return {
        "period_a": {"days": 0, "total_value": 0.0, "total_cost": 0.0, "roi_percent": 0.0},
        "period_b": {"days": 0, "total_value": 0.0, "total_cost": 0.0, "roi_percent": 0.0},
        "delta": {
            "value_change": 0.0,
            "cost_change": 0.0,
            "roi_change": 0.0,
            "value_pct_change": 0.0,
            "cost_pct_change": 0.0,
        },
    }
