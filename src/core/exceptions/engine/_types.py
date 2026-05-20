"""Types and constants for engine."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..taxonomy import ExceptionCategory, ExceptionSeverity

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3

_BASE_DELAY = 0.1  # seconds


@dataclass
class ExceptionSignal:
    """An immutable snapshot of an exception event flowing through the system."""

    signal_id: str = ""
    source: str = ""
    category: ExceptionCategory = ExceptionCategory.SYSTEM_ERROR
    severity: ExceptionSeverity = ExceptionSeverity.ERROR
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.signal_id:
            self.signal_id = f"sig-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class ExceptionRecord:
    """A persisted record linking a signal to its routing outcome."""

    record_id: str = ""
    signal: Optional[ExceptionSignal] = None
    routing_action: str = ""
    resolved: bool = False
    resolved_at: str = ""
    resolution_note: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"rec-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "record_id": self.record_id,
            "signal": self.signal.to_dict() if self.signal else None,
            "routing_action": self.routing_action,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "resolution_note": self.resolution_note,
        }


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _zenic_exceptions (
    record_id       TEXT PRIMARY KEY,
    signal_id       TEXT NOT NULL,
    source          TEXT NOT NULL,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL DEFAULT '',
    context_json    TEXT NOT NULL DEFAULT '{}',
    timestamp       TEXT NOT NULL DEFAULT '',
    routing_action  TEXT NOT NULL DEFAULT '',
    resolved        INTEGER NOT NULL DEFAULT 0,
    resolved_at     TEXT NOT NULL DEFAULT '',
    resolution_note TEXT NOT NULL DEFAULT '',
    tenant_id       TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_zenic_exc_cat
ON _zenic_exceptions(category);

CREATE INDEX IF NOT EXISTS idx_zenic_exc_sev
ON _zenic_exceptions(severity);

CREATE INDEX IF NOT EXISTS idx_zenic_exc_ts
ON _zenic_exceptions(timestamp);

CREATE INDEX IF NOT EXISTS idx_zenic_exc_tenant
ON _zenic_exceptions(tenant_id);

CREATE INDEX IF NOT EXISTS idx_zenic_exc_resolved
ON _zenic_exceptions(resolved);
"""
