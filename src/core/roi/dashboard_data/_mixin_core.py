"""
Dashboard Data — Core ROIDashboardData class.

Aggregates cost, value, and impact data into executive dashboard metrics.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List

from ._types import TrendPoint, DashboardWidget
from ._mixin_trends import DashboardTrendsMixin

logger = logging.getLogger(__name__)


class ROIDashboardData(DashboardTrendsMixin):
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
                from ..cost_accumulator import get_cost_accumulator
                self._cost_accumulator = get_cost_accumulator()
            except Exception as exc:
                logger.error("ROIDashboardData: CostAccumulator unavailable: %s", exc)
        return self._cost_accumulator

    def _get_value_tracker(self) -> Any:
        """Lazy-load the ValueTracker singleton."""
        if self._value_tracker is None:
            try:
                from ..value_tracker import get_value_tracker
                self._value_tracker = get_value_tracker()
            except Exception as exc:
                logger.error("ROIDashboardData: ValueTracker unavailable: %s", exc)
        return self._value_tracker

    def _get_impact_scorer(self) -> Any:
        """Lazy-load the ImpactScorer singleton."""
        if self._impact_scorer is None:
            try:
                from ..impact_scorer import get_impact_scorer
                self._impact_scorer = get_impact_scorer()
            except Exception as exc:
                logger.error("ROIDashboardData: ImpactScorer unavailable: %s", exc)
        return self._impact_scorer

    # ── Metrics ─────────────────────────────────────────

    def get_metrics(self, tenant_id: str = "") -> Dict[str, Any]:
        """Return aggregated ROI metrics."""
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

    # ── Internal helpers ────────────────────────────────

    @staticmethod
    def _value_cat(name: str) -> Any:
        """Get ValueCategory enum by name (lazy import)."""
        try:
            from ..value_tracker import ValueCategory
            return ValueCategory(name)
        except Exception:
            return None

    @staticmethod
    def _unit_val(name: str) -> float:
        """Get default unit value by category name (lazy import)."""
        try:
            from ..value_tracker import ValueCategory, DEFAULT_UNIT_VALUES
            cat = ValueCategory(name)
            return DEFAULT_UNIT_VALUES.get(cat, 1.0)
        except Exception:
            return 1.0
