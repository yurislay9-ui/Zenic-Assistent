"""
A15 DataAnalyzer — SINGLE RESPONSIBILITY: Perform statistical analysis and pattern detection.

Deterministic data analysis: descriptive statistics, trend detection, insight generation.
No AI. Pure mathematical operations on data.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from ..resilience import BaseAgent
from ..schemas import AnalyticsResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

SUPPORTED_METRICS = frozenset({
    "count", "min", "max", "avg", "sum",
    "median", "stdev", "variance", "range",
})

MAX_DATASET_SIZE = 5000
TREND_WINDOW = 5  # Window size for simple trend detection


class DataAnalyzer(BaseAgent[AnalyticsResult]):
    """
    A15: Perform statistical analysis and pattern detection.

    Single Responsibility: Data analysis ONLY.
    Method: Deterministic descriptive statistics + trend detection.
    Fallback: Empty AnalyticsResult with no metrics.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A15_DataAnalyzer", **kwargs)

    def execute(self, input_data: Any) -> AnalyticsResult:
        """
        Analyze data: compute metrics, detect trends, generate insights.

        Input (BusinessData.data dict):
            - data / items: list of records (dicts or numbers)
            - metrics: list of metric names to compute
            - field: str (specific numeric field to analyze, optional)

        Output: AnalyticsResult with metrics, trends, insights.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        dataset = data.get("data", data.get("items", []))
        requested_metrics = data.get("metrics", ["count", "min", "max", "avg"])
        target_field = data.get("field", None)

        if not isinstance(dataset, list):
            dataset = [dataset]

        # Cap dataset size
        dataset = dataset[:MAX_DATASET_SIZE]

        metrics: dict[str, float] = {}
        trends: list[str] = []
        insights: list[str] = []

        # ── Basic count ──
        count = len(dataset)
        metrics["count"] = float(count)

        if count == 0:
            return AnalyticsResult(
                metrics=metrics, trends=[], insights=["Empty dataset"],
                source="deterministic",
            )

        # ── Extract numeric values ──
        values = self._extract_numeric_values(dataset, target_field)

        if not values:
            insights.append("No numeric data found for analysis")
            return AnalyticsResult(
                metrics=metrics, trends=trends, insights=insights,
                source="deterministic",
            )

        # ── Compute requested metrics ──
        for metric in requested_metrics:
            if metric == "min":
                metrics["min"] = min(values)
            elif metric == "max":
                metrics["max"] = max(values)
            elif metric == "avg":
                metrics["avg"] = round(sum(values) / len(values), 4)
            elif metric == "sum":
                metrics["sum"] = sum(values)
            elif metric == "median":
                metrics["median"] = self._median(values)
            elif metric == "stdev":
                metrics["stdev"] = self._stdev(values)
            elif metric == "variance":
                metrics["variance"] = self._variance(values)
            elif metric == "range":
                metrics["range"] = max(values) - min(values)

        # ── Trend detection (simple moving average comparison) ──
        if len(values) >= TREND_WINDOW * 2:
            first_half = values[:len(values) // 2]
            second_half = values[len(values) // 2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)

            change_pct = ((avg_second - avg_first) / avg_first * 100) if avg_first != 0 else 0

            if change_pct > 5:
                trends.append(f"UPWARD: +{change_pct:.1f}% trend detected")
            elif change_pct < -5:
                trends.append(f"DOWNWARD: {change_pct:.1f}% trend detected")
            else:
                trends.append(f"STABLE: {change_pct:+.1f}% change (no significant trend)")

        # ── Generate insights ──
        insights.append(f"Analyzed {count} records with {len(values)} numeric values")

        if "min" in metrics and "max" in metrics:
            spread = metrics["max"] - metrics["min"]
            insights.append(f"Value range: {spread:.2f} (min={metrics['min']:.2f}, max={metrics['max']:.2f})")

        if "stdev" in metrics and "avg" in metrics:
            cv = (metrics["stdev"] / metrics["avg"] * 100) if metrics["avg"] != 0 else 0
            if cv > 50:
                insights.append(f"HIGH VARIABILITY: Coefficient of variation = {cv:.1f}%")
            elif cv < 10:
                insights.append(f"LOW VARIABILITY: Coefficient of variation = {cv:.1f}%")

        # Limit insights
        insights = insights[:5]

        return AnalyticsResult(
            metrics=metrics,
            trends=trends,
            insights=insights,
            source="deterministic",
        )

    @staticmethod
    def _extract_numeric_values(dataset: list, field: Optional[str] = None) -> list[float]:
        """Extract numeric values from dataset. If field is specified, extract that field only."""
        values = []

        for item in dataset:
            if isinstance(item, (int, float)):
                values.append(float(item))
            elif isinstance(item, dict) and field:
                val = item.get(field)
                if isinstance(val, (int, float)):
                    values.append(float(val))
            elif isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, (int, float)):
                        values.append(float(v))

        return values

    @staticmethod
    def _median(values: list[float]) -> float:
        """Compute median of a list of values."""
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mid = n // 2
        if n % 2 == 0:
            return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
        return sorted_vals[mid]

    @staticmethod
    def _variance(values: list[float]) -> float:
        """Compute population variance."""
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        return sum((x - avg) ** 2 for x in values) / len(values)

    @classmethod
    def _stdev(cls, values: list[float]) -> float:
        """Compute population standard deviation."""
        if len(values) < 2:
            return 0.0
        return math.sqrt(cls._variance(values))

    def fallback(self, input_data: Any) -> AnalyticsResult:
        """Safe fallback: empty analytics result."""
        return AnalyticsResult(
            metrics={}, trends=[], insights=[],
            source="fallback",
        )
