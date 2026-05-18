"""routing — Type definitions."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .engine import ExceptionEngine, ExceptionSignal
from .taxonomy import ExceptionCategory, ExceptionSeverity

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingAction",
    "RoutingRule",
    "ExceptionRouter",
    "get_exception_router",
    "reset_exception_router",
]

# ── Retry helper ──────────────────────────────────────────────

_MAX_RETRIES = 3
_BASE_DELAY = 0.1


def _retry_db(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Execute *fn* with exponential-backoff retry on DB errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionRouter: DB retry %d/%d after %.2fs – %s",
                attempt + 1, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
        except sqlite3.Error as exc:
            last_exc = exc
            delay = _BASE_DELAY * (2 ** attempt)
            logger.warning(
                "ExceptionRouter: DB error retry %d/%d – %s",
                attempt + 1, _MAX_RETRIES, exc,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc  # type: ignore[misc]


# ── RoutingAction enum ────────────────────────────────────────


class RoutingAction(str, Enum):
    """Actions that can be taken when an exception is routed."""

    ESCALATE_HUMAN = "ESCALATE_HUMAN"
    PAUSE_AUTOMATION = "PAUSE_AUTOMATION"
    DEGRADE_SYSTEM = "DEGRADE_SYSTEM"
    RETRY_WITH_BACKOFF = "RETRY_WITH_BACKOFF"
    NOTIFY_ADMIN = "NOTIFY_ADMIN"
    ABORT_ACTION = "ABORT_ACTION"
    LOG_AND_CONTINUE = "LOG_AND_CONTINUE"
    REROUTE = "REROUTE"


# ── Severity ordering for rule matching ───────────────────────

_SEVERITY_ORDER: Dict[ExceptionSeverity, int] = {
    ExceptionSeverity.INFO: 0,
    ExceptionSeverity.WARNING: 1,
    ExceptionSeverity.ERROR: 2,
    ExceptionSeverity.CRITICAL: 3,
    ExceptionSeverity.FATAL: 4,
}


# ── RoutingRule dataclass ─────────────────────────────────────


@dataclass
class RoutingRule:
    """A rule that maps exception signals to routing actions.

    A rule matches a signal when:
      - The signal's category equals the rule's category
      - The signal's severity falls between min_severity and max_severity
      - Any extra conditions in ``conditions`` are satisfied
    """

    rule_id: str = ""
    category: ExceptionCategory = ExceptionCategory.SYSTEM_ERROR
    min_severity: ExceptionSeverity = ExceptionSeverity.INFO
    max_severity: ExceptionSeverity = ExceptionSeverity.FATAL
    action: RoutingAction = RoutingAction.LOG_AND_CONTINUE
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = f"rule-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "rule_id": self.rule_id,
            "category": self.category.value,
            "min_severity": self.min_severity.value,
            "max_severity": self.max_severity.value,
            "action": self.action.value,
            "conditions": self.conditions,
            "priority": self.priority,
            "enabled": self.enabled,
        }

    def matches(self, signal: ExceptionSignal) -> bool:
        """Return ``True`` if *signal* satisfies this rule's criteria."""
        if not self.enabled:
            return False
        if signal.category != self.category:
            return False
        sig_level = _SEVERITY_ORDER.get(signal.severity, 0)
        min_level = _SEVERITY_ORDER.get(self.min_severity, 0)
        max_level = _SEVERITY_ORDER.get(self.max_severity, 0)
        if sig_level < min_level or sig_level > max_level:
            return False
        # Check extra conditions against signal context
        for key, expected in self.conditions.items():
            actual = signal.context.get(key)
            if actual != expected:
                return False
        return True


# ── Schema DDL ────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _zenic_routing_rules (
    rule_id        TEXT PRIMARY KEY,
    category       TEXT NOT NULL,
    min_severity   TEXT NOT NULL,
    max_severity   TEXT NOT NULL,
    action         TEXT NOT NULL,
    conditions_json TEXT NOT NULL DEFAULT '{}',
    priority       INTEGER NOT NULL DEFAULT 0,
    enabled        INTEGER NOT NULL DEFAULT 1
);
"""


# ── ExceptionRouter ───────────────────────────────────────────

