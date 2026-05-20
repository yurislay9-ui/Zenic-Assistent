"""
Zenic-Agents ROI — Dashboard Data Aggregator

Aggregates cost, value, and impact data from CostAccumulator,
ValueTracker, and ImpactScorer into executive dashboard metrics,
widgets, trends, and comparison reports.  Uses lazy loading to
avoid circular imports.
"""

import threading
from typing import Any, Optional

from ._types import TrendPoint, DashboardWidget
from ._mixin_core import ROIDashboardData

__all__ = [
    "TrendPoint",
    "DashboardWidget",
    "ROIDashboardData",
    "get_roi_dashboard_data",
    "reset_roi_dashboard_data",
]


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
