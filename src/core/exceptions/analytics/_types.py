"""Types and constants for analytics."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..taxonomy import ExceptionCategory, ExceptionSeverity

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

_BASE_DELAY = 0.1


@dataclass
class ExceptionPattern:
    """A recurring exception pattern detected by the analytics engine."""

    pattern_id: str = ""
    category: ExceptionCategory = ExceptionCategory.SYSTEM_ERROR
    source: str = ""
    frequency: int = 0
    avg_interval_seconds: float = 0.0
    first_seen: str = ""
    last_seen: str = ""
    trend: str = "stable"  # "increasing" | "stable" | "decreasing"
    sample_messages: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.pattern_id:
            self.pattern_id = f"pat-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "category": self.category.value,
            "source": self.source,
            "frequency": self.frequency,
            "avg_interval_seconds": self.avg_interval_seconds,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "trend": self.trend,
            "sample_messages": self.sample_messages,
        }


@dataclass
class AnalyticsSnapshot:
    """Point-in-time aggregate view of exception analytics."""

    total_exceptions: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)
    top_patterns: List[ExceptionPattern] = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""
    exception_rate_per_hour: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "total_exceptions": self.total_exceptions,
            "by_category": self.by_category,
            "by_severity": self.by_severity,
            "by_source": self.by_source,
            "top_patterns": [p.to_dict() for p in self.top_patterns],
            "period_start": self.period_start,
            "period_end": self.period_end,
            "exception_rate_per_hour": self.exception_rate_per_hour,
        }


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _zenic_analytics_signals (
    signal_id   TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    category    TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL DEFAULT '',
    context_json TEXT NOT NULL DEFAULT '{}',
    timestamp   TEXT NOT NULL DEFAULT '',
    tenant_id   TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_zenic_analytics_cat
ON _zenic_analytics_signals(category);

CREATE INDEX IF NOT EXISTS idx_zenic_analytics_sev
ON _zenic_analytics_signals(severity);

CREATE INDEX IF NOT EXISTS idx_zenic_analytics_ts
ON _zenic_analytics_signals(timestamp);

CREATE INDEX IF NOT EXISTS idx_zenic_analytics_tenant
ON _zenic_analytics_signals(tenant_id);
"""
