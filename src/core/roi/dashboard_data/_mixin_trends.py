"""
Dashboard Data — Trends and comparison mixin.

Contains get_trend, get_comparison, and export_data methods.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ._types import TrendPoint

import logging
logger = logging.getLogger(__name__)


class DashboardTrendsMixin:
    """Mixin providing trend, comparison, and export methods for ROIDashboardData."""

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
                        from ..value_tracker import ValueCategory, DEFAULT_UNIT_VALUES
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
                        from ..value_tracker import ValueCategory, DEFAULT_UNIT_VALUES
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

            a_start = time.strftime(
                "%Y-%m-%dT00:00:00Z", time.gmtime(now - period_a_days * 86400)
            )
            b_start = time.strftime(
                "%Y-%m-%dT00:00:00Z",
                time.gmtime(now - (period_a_days + period_b_days) * 86400),
            )
            b_end = a_start

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

    def export_data(self, format: str = "json") -> str:
        """Export all dashboard data as JSON."""
        import json

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
            return json.dumps(data, indent=2, default=str)
