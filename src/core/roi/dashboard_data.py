"""
Zenic-Agents ROI — Dashboard Data Aggregator

Aggregates cost, value, and impact data from CostAccumulator,
ValueTracker, and ImpactScorer into executive dashboard metrics,
widgets, trends, and comparison reports.  Uses lazy loading to
avoid circular imports.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

__all__ = [
    "TrendPoint",
    "DashboardWidget",
    "ROIDashboardData",
    "get_roi_dashboard_data",
    "reset_roi_dashboard_data",
]


# ── Data models ─────────────────────────────────────────


@dataclass
class TrendPoint:
    """A single point in a time-series trend."""

    timestamp: str = ""
    value: float = 0.0
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "timestamp": self.timestamp,
            "value": self.value,
            "label": self.label,
        }


@dataclass
class DashboardWidget:
    """A dashboard widget descriptor for the frontend."""

    widget_id: str = ""
    title: str = ""
    widget_type: str = "metric"  # "metric" | "chart" | "table" | "trend"
    data: Dict[str, Any] = field(default_factory=dict)
    position: int = 0
    refresh_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "widget_id": self.widget_id,
            "title": self.title,
            "widget_type": self.widget_type,
            "data": self.data,
            "position": self.position,
            "refresh_seconds": self.refresh_seconds,
        }


# ── ROIDashboardData ────────────────────────────────────


class ROIDashboardData:
    """Aggregates all ROI data for the executive dashboard.

    Lazy-loads CostAccumulator, ValueTracker, and ImpactScorer
    to avoid circular imports and keep instantiation lightweight.

    Usage::

        dashboard = ROIDashboardData()
        metrics = dashboard.get_metrics()
        widgets = dashboard.get_widgets()
        trend = dashboard.get_trend("cost", days=30)
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cost_accumulator: Any = None
        self._value_tracker: Any = None
        self._impact_scorer: Any = None

    # ── Lazy loaders ────────────────────────────────────

    def _get_cost_accumulator(self) -> Any:
        """Lazy-load the CostAccumulator singleton."""
        if self._cost_accumulator is None:
            try:
                from .cost_accumulator import get_cost_accumulator
                self._cost_accumulator = get_cost_accumulator()
            except Exception as exc:
                logger.error("ROIDashboardData: CostAccumulator unavailable: %s", exc)
        return self._cost_accumulator

    def _get_value_tracker(self) -> Any:
        """Lazy-load the ValueTracker singleton."""
        if self._value_tracker is None:
            try:
                from .value_tracker import get_value_tracker
                self._value_tracker = get_value_tracker()
            except Exception as exc:
                logger.error("ROIDashboardData: ValueTracker unavailable: %s", exc)
        return self._value_tracker

    def _get_impact_scorer(self) -> Any:
        """Lazy-load the ImpactScorer singleton."""
        if self._impact_scorer is None:
            try:
                from .impact_scorer import get_impact_scorer
                self._impact_scorer = get_impact_scorer()
            except Exception as exc:
                logger.error("ROIDashboardData: ImpactScorer unavailable: %s", exc)
        return self._impact_scorer

    # ── Metrics ─────────────────────────────────────────

    def get_metrics(self, tenant_id: str = "") -> Dict[str, Any]:
        """Return aggregated ROI metrics.

        Includes:
        - Total hours saved, errors avoided, revenue recovered, tasks automated
        - ROI percentage, net value
        - Cost breakdown
        """
        with self._lock:
            metrics: Dict[str, Any] = {
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

            # Value metrics
            vt = self._get_value_tracker()
            if vt is not None:
                try:
                    metrics["hours_saved"] = vt.get_total_value(
                        category=self._value_cat("hours_saved"),
                        tenant_id=tenant_id,
                    ) / max(
                        self._unit_val("hours_saved"), 1.0
                    )
                    metrics["errors_avoided"] = int(
                        vt.get_total_value(
                            category=self._value_cat("errors_avoided"),
                            tenant_id=tenant_id,
                        ) / max(
                            self._unit_val("errors_avoided"), 1.0
                        )
                    )
                    metrics["revenue_recovered"] = vt.get_total_value(
                        category=self._value_cat("revenue_recovered"),
                        tenant_id=tenant_id,
                    )
                    metrics["tasks_automated"] = int(
                        vt.get_total_value(
                            category=self._value_cat("tasks_automated"),
                            tenant_id=tenant_id,
                        ) / max(
                            self._unit_val("tasks_automated"), 1.0
                        )
                    )
                    metrics["total_value"] = vt.get_total_value(tenant_id=tenant_id)
                    metrics["value_breakdown"] = vt.get_value_breakdown(tenant_id=tenant_id)
                except Exception as exc:
                    logger.error("ROIDashboardData: value metrics failed: %s", exc)

            # Cost metrics
            ca = self._get_cost_accumulator()
            if ca is not None:
                try:
                    metrics["total_cost"] = ca.get_total_cost(tenant_id=tenant_id)
                    metrics["cost_breakdown"] = ca.get_cost_breakdown(tenant_id=tenant_id)
                except Exception as exc:
                    logger.error("ROIDashboardData: cost metrics failed: %s", exc)

            # ROI
            total_value = metrics.get("total_value", 0.0)
            total_cost = metrics.get("total_cost", 0.0)
            if total_cost > 0:
                metrics["roi_percent"] = round(
                    ((total_value - total_cost) / total_cost) * 100, 2
                )
            metrics["net_value"] = round(total_value - total_cost, 2)

            # Impact summary
            iscorer = self._get_impact_scorer()
            if iscorer is not None:
                try:
                    metrics["impact_summary"] = iscorer.get_impact_summary()
                except Exception as exc:
                    logger.error("ROIDashboardData: impact summary failed: %s", exc)

            return metrics

    # ── Widgets ─────────────────────────────────────────

    def get_widgets(self, tenant_id: str = "") -> List[DashboardWidget]:
        """Return the pre-configured dashboard widget set."""
        with self._lock:
            widgets: List[DashboardWidget] = []

            # 1. ROI Overview — metric
            metrics = self.get_metrics(tenant_id=tenant_id)
            widgets.append(DashboardWidget(
                widget_id="roi_overview",
                title="ROI Overview",
                widget_type="metric",
                data={
                    "value": metrics.get("roi_percent", 0.0),
                    "suffix": "%",
                    "subtitle": "Return on Investment",
                },
                position=1,
                refresh_seconds=60,
            ))

            # 2. Hours Saved — metric
            widgets.append(DashboardWidget(
                widget_id="hours_saved",
                title="Hours Saved",
                widget_type="metric",
                data={
                    "value": metrics.get("hours_saved", 0.0),
                    "suffix": "hrs",
                    "subtitle": "By Automation",
                },
                position=2,
                refresh_seconds=60,
            ))

            # 3. Revenue Recovered — metric
            widgets.append(DashboardWidget(
                widget_id="revenue_recovered",
                title="Revenue Recovered",
                widget_type="metric",
                data={
                    "value": metrics.get("revenue_recovered", 0.0),
                    "prefix": "$",
                    "subtitle": "Total USD",
                },
                position=3,
                refresh_seconds=60,
            ))

            # 4. Cost Trend — chart
            ca = self._get_cost_accumulator()
            daily_costs = ca.get_daily_costs(days=30) if ca is not None else []
            widgets.append(DashboardWidget(
                widget_id="cost_trend",
                title="Cost Trend",
                widget_type="chart",
                data={
                    "type": "line",
                    "labels": [d.get("date", "") for d in daily_costs],
                    "values": [d.get("cost", 0) for d in daily_costs],
                    "y_label": "USD",
                },
                position=4,
                refresh_seconds=300,
            ))

            # 5. Value Trend — chart
            vt = self._get_value_tracker()
            daily_values = vt.get_daily_value(days=30) if vt is not None else []
            widgets.append(DashboardWidget(
                widget_id="value_trend",
                title="Value Trend",
                widget_type="chart",
                data={
                    "type": "line",
                    "labels": [d.get("date", "") for d in daily_values],
                    "values": [d.get("value", 0) for d in daily_values],
                    "y_label": "USD",
                },
                position=5,
                refresh_seconds=300,
            ))

            # 6. Top Impacts — table
            iscorer = self._get_impact_scorer()
            top_impacts = []
            if iscorer is not None:
                try:
                    scores = iscorer.get_urgent_actions(max_urgency_hours=72)
                    for s in scores[:5]:
                        top_impacts.append(s.to_dict())
                except Exception as exc:
                    logger.error("ROIDashboardData: top impacts failed: %s", exc)

            widgets.append(DashboardWidget(
                widget_id="top_impacts",
                title="Top Impacts",
                widget_type="table",
                data={
                    "columns": ["impact_type", "loss", "gain", "urgency", "score"],
                    "rows": top_impacts,
                },
                position=6,
                refresh_seconds=120,
            ))

            # 7. Category Breakdown — chart
            widgets.append(DashboardWidget(
                widget_id="category_breakdown",
                title="Category Breakdown",
                widget_type="chart",
                data={
                    "type": "bar",
                    "labels": list(metrics.get("value_breakdown", {}).keys()),
                    "values": list(metrics.get("value_breakdown", {}).values()),
                    "y_label": "USD",
                },
                position=7,
                refresh_seconds=300,
            ))

            return widgets

    # ── Trends ──────────────────────────────────────────

    def get_trend(
        self,
        metric: str,
        days: int = 30,
    ) -> List[TrendPoint]:
        """Return trend data for a specific metric over the given period.

        Available metrics: ``cost``, ``value``, ``roi``,
        ``hours_saved``, ``errors_avoided``.
        """
        with self._lock:
            points: List[TrendPoint] = []
            metric_lower = metric.lower()

            if metric_lower == "cost":
                ca = self._get_cost_accumulator()
                if ca is not None:
                    try:
                        for d in ca.get_daily_costs(days=days):
                            points.append(TrendPoint(
                                timestamp=d.get("date", ""),
                                value=d.get("cost", 0.0),
                                label=d.get("date", ""),
                            ))
                    except Exception as exc:
                        logger.error("ROIDashboardData: cost trend failed: %s", exc)

            elif metric_lower == "value":
                vt = self._get_value_tracker()
                if vt is not None:
                    try:
                        for d in vt.get_daily_value(days=days):
                            points.append(TrendPoint(
                                timestamp=d.get("date", ""),
                                value=d.get("value", 0.0),
                                label=d.get("date", ""),
                            ))
                    except Exception as exc:
                        logger.error("ROIDashboardData: value trend failed: %s", exc)

            elif metric_lower == "roi":
                ca = self._get_cost_accumulator()
                vt = self._get_value_tracker()
                if ca is not None and vt is not None:
                    try:
                        cost_days = {d["date"]: d["cost"] for d in ca.get_daily_costs(days=days)}
                        value_days = {d["date"]: d["value"] for d in vt.get_daily_value(days=days)}
                        all_dates = sorted(set(cost_days.keys()) | set(value_days.keys()))
                        for dt in all_dates:
                            c = cost_days.get(dt, 0.0)
                            v = value_days.get(dt, 0.0)
                            roi = ((v - c) / c * 100) if c > 0 else 0.0
                            points.append(TrendPoint(
                                timestamp=dt, value=round(roi, 2), label=dt,
                            ))
                    except Exception as exc:
                        logger.error("ROIDashboardData: roi trend failed: %s", exc)

            elif metric_lower == "hours_saved":
                vt = self._get_value_tracker()
                if vt is not None:
                    try:
                        from .value_tracker import ValueCategory, DEFAULT_UNIT_VALUES
                        uv = DEFAULT_UNIT_VALUES.get(ValueCategory.HOURS_SAVED, 25.0)
                        for d in vt.get_daily_value(days=days):
                            points.append(TrendPoint(
                                timestamp=d.get("date", ""),
                                value=round(d.get("value", 0.0) / max(uv, 1.0), 2),
                                label=d.get("date", ""),
                            ))
                    except Exception as exc:
                        logger.error("ROIDashboardData: hours_saved trend failed: %s", exc)

            elif metric_lower == "errors_avoided":
                vt = self._get_value_tracker()
                if vt is not None:
                    try:
                        from .value_tracker import ValueCategory, DEFAULT_UNIT_VALUES
                        uv = DEFAULT_UNIT_VALUES.get(ValueCategory.ERRORS_AVOIDED, 150.0)
                        for d in vt.get_daily_value(days=days):
                            points.append(TrendPoint(
                                timestamp=d.get("date", ""),
                                value=round(d.get("value", 0.0) / max(uv, 1.0), 0),
                                label=d.get("date", ""),
                            ))
                    except Exception as exc:
                        logger.error("ROIDashboardData: errors_avoided trend failed: %s", exc)

            else:
                logger.warning("ROIDashboardData: unknown trend metric '%s'", metric)

            return points

    # ── Comparison ──────────────────────────────────────

    def get_comparison(
        self,
        period_a_days: int,
        period_b_days: int,
    ) -> Dict[str, Any]:
        """Compare two time periods for ROI trends.

        Period A is the more recent period, Period B is the older one.
        Returns deltas and percentage changes.
        """
        with self._lock:
            now = time.time()

            # Period A: last period_a_days days
            a_start = time.strftime(
                "%Y-%m-%dT00:00:00Z", time.gmtime(now - period_a_days * 86400)
            )
            # Period B: period_b_days before Period A
            b_start = time.strftime(
                "%Y-%m-%dT00:00:00Z",
                time.gmtime(now - (period_a_days + period_b_days) * 86400),
            )
            b_end = a_start  # Period B ends where Period A begins

            a_value: float = 0.0
            a_cost: float = 0.0
            b_value: float = 0.0
            b_cost: float = 0.0

            vt = self._get_value_tracker()
            if vt is not None:
                try:
                    a_value = vt.get_total_value(from_time=a_start)
                    b_value = vt.get_total_value(from_time=b_start, to_time=b_end)
                except Exception as exc:
                    logger.error("ROIDashboardData: comparison value failed: %s", exc)

            ca = self._get_cost_accumulator()
            if ca is not None:
                try:
                    a_cost = ca.get_total_cost(from_time=a_start)
                    b_cost = ca.get_total_cost(from_time=b_start, to_time=b_end)
                except Exception as exc:
                    logger.error("ROIDashboardData: comparison cost failed: %s", exc)

            a_roi = ((a_value - a_cost) / a_cost * 100) if a_cost > 0 else 0.0
            b_roi = ((b_value - b_cost) / b_cost * 100) if b_cost > 0 else 0.0

            def _pct_change(new: float, old: float) -> float:
                if old == 0:
                    return 0.0
                return round(((new - old) / old) * 100, 2)

            return {
                "period_a": {
                    "days": period_a_days,
                    "total_value": round(a_value, 2),
                    "total_cost": round(a_cost, 2),
                    "roi_percent": round(a_roi, 2),
                },
                "period_b": {
                    "days": period_b_days,
                    "total_value": round(b_value, 2),
                    "total_cost": round(b_cost, 2),
                    "roi_percent": round(b_roi, 2),
                },
                "delta": {
                    "value_change": round(a_value - b_value, 2),
                    "cost_change": round(a_cost - b_cost, 2),
                    "roi_change": round(a_roi - b_roi, 2),
                    "value_pct_change": _pct_change(a_value, b_value),
                    "cost_pct_change": _pct_change(a_cost, b_cost),
                },
            }

    # ── Export ──────────────────────────────────────────

    def export_data(self, format: str = "json") -> str:
        """Export all dashboard data as JSON.

        Currently only JSON format is supported.
        """
        with self._lock:
            data = {
                "metrics": self.get_metrics(),
                "widgets": [w.to_dict() for w in self.get_widgets()],
                "trends": {
                    "cost": [p.to_dict() for p in self.get_trend("cost")],
                    "value": [p.to_dict() for p in self.get_trend("value")],
                    "roi": [p.to_dict() for p in self.get_trend("roi")],
                },
                "comparison": self.get_comparison(7, 7),
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if format == "json":
                return json.dumps(data, indent=2, default=str)
            # Fallback to JSON for unknown formats
            return json.dumps(data, indent=2, default=str)

    # ── Internal helpers ────────────────────────────────

    @staticmethod
    def _value_cat(name: str) -> Any:
        """Get ValueCategory enum by name (lazy import)."""
        try:
            from .value_tracker import ValueCategory
            return ValueCategory(name)
        except Exception:
            return None

    @staticmethod
    def _unit_val(name: str) -> float:
        """Get default unit value by category name (lazy import)."""
        try:
            from .value_tracker import ValueCategory, DEFAULT_UNIT_VALUES
            cat = ValueCategory(name)
            return DEFAULT_UNIT_VALUES.get(cat, 1.0)
        except Exception:
            return 1.0


# ── Singleton ────────────────────────────────────────────

_roi_dashboard_data: Optional[ROIDashboardData] = None
_lock = threading.Lock()


def get_roi_dashboard_data(**kwargs: Any) -> ROIDashboardData:
    """Get or create the global ROIDashboardData singleton."""
    global _roi_dashboard_data
    with _lock:
        if _roi_dashboard_data is None:
            _roi_dashboard_data = ROIDashboardData(**kwargs)
        return _roi_dashboard_data


def reset_roi_dashboard_data() -> None:
    """Reset the global ROIDashboardData (for testing)."""
    global _roi_dashboard_data
    _roi_dashboard_data = None
