"""
KPI Tracker — Data models for KPI measurements and trends.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class KPIMeasurement:
    """A single KPI measurement for an objective's metric.

    Records the current value of a metric along with the target and
    the delta from the previous measurement, enabling trend analysis.
    """
    measurement_id: str = ""
    objective_id: str = ""
    metric_name: str = ""
    value: float = 0.0
    target_value: float = 0.0
    unit: str = ""
    timestamp: str = ""
    source: str = "manual"
    delta_from_last: float = 0.0

    def __post_init__(self) -> None:
        """Auto-generate ID and timestamp if not provided."""
        if not self.measurement_id:
            self.measurement_id = f"kpi-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def gap(self) -> float:
        """Calculate the gap between target and current value.

        Returns:
            target_value - value (positive means still need to improve).
        """
        return self.target_value - self.value

    def is_improving(self) -> bool:
        """Check if the metric is improving.

        For metrics where target > current: positive delta means improving.
        For metrics where target < current: negative delta means improving.
        A positive delta_from_last always means the value increased.

        Returns:
            True if the measurement shows improvement toward the target.
        """
        if self.delta_from_last == 0.0:
            return False
        # If target is higher than current, increasing value = improving
        if self.target_value > self.value:
            return self.delta_from_last > 0
        # If target is lower than current, decreasing value = improving
        return self.delta_from_last < 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "measurement_id": self.measurement_id,
            "objective_id": self.objective_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "target_value": self.target_value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "source": self.source,
            "delta_from_last": self.delta_from_last,
        }


@dataclass
class KPITrend:
    """Trend analysis for a KPI metric over time.

    Includes linear regression slope for trend direction and
    projected achievement date based on rate of change.
    """
    metric_name: str = ""
    values: List[float] = field(default_factory=list)
    timestamps: List[str] = field(default_factory=list)
    trend_direction: str = "stable"  # "improving" | "stable" | "declining"
    avg_rate_of_change: float = 0.0
    projected_achievement_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "metric_name": self.metric_name,
            "values": self.values,
            "timestamps": self.timestamps,
            "trend_direction": self.trend_direction,
            "avg_rate_of_change": self.avg_rate_of_change,
            "projected_achievement_date": self.projected_achievement_date,
        }
