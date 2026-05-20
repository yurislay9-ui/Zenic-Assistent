"""
Dashboard Data — Types.

Contains TrendPoint and DashboardWidget dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


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
