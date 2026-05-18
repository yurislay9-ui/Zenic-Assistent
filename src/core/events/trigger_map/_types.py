"""Types and constants for trigger_map."""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("zenic_agents.events.trigger_map")

DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")

DB_PATH = os.path.join(DB_DIR, "trigger_map.sqlite")

_MISSING = object()


class ConditionOperator(str, Enum):
    """Supported condition operators for event data filtering."""
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    CONTAINS = "contains"
    IN = "in"


@dataclass
class TriggerCondition:
    """
    A single condition that event_data must satisfy for a trigger to fire.

    Attributes:
        field: Dot-notation path into event_data (e.g. "value", "meta.severity").
        operator: Comparison operator (eq, neq, gt, lt, contains, in).
        value: The value to compare against.
    """
    field: str
    operator: ConditionOperator = ConditionOperator.EQ
    value: Any = None

    def evaluate(self, event_data: dict[str, Any]) -> bool:
        """
        Evaluate this condition against the given event_data.

        Supports dot-notation field paths (e.g. "meta.severity").
        """
        actual = _resolve_field(self.field, event_data)
        if actual is _MISSING:
            return False

        try:
            if self.operator == ConditionOperator.EQ:
                return actual == self.value
            elif self.operator == ConditionOperator.NEQ:
                return actual != self.value
            elif self.operator == ConditionOperator.GT:
                return float(actual) > float(self.value)
            elif self.operator == ConditionOperator.LT:
                return float(actual) < float(self.value)
            elif self.operator == ConditionOperator.CONTAINS:
                if isinstance(actual, str):
                    return str(self.value) in actual
                if isinstance(actual, (list, tuple)):
                    return self.value in actual
                return False
            elif self.operator == ConditionOperator.IN:
                if isinstance(self.value, (list, tuple, set)):
                    return actual in self.value
                return False
            else:
                logger.warning(
                    "TriggerCondition: unknown operator %s", self.operator,
                )
                return False
        except (TypeError, ValueError) as exc:
            logger.debug(
                "TriggerCondition: error evaluating %s %s %s: %s",
                self.field, self.operator, self.value, exc,
            )
            return False


@dataclass
class TriggerMapping:
    """
    A declarative mapping from an event pattern to an automation.

    Attributes:
        trigger_id: Unique identifier.
        event_pattern: Wildcard pattern (e.g. "db.*", "sna.stock.**").
        automation_id: The automation to invoke when matched.
        priority: Higher priority mappings fire first.
        condition: Optional list of conditions on event_data.
        enabled: Whether this mapping is active.
        created_at: Unix timestamp.
    """
    trigger_id: str
    event_pattern: str
    automation_id: str
    priority: int = 0
    condition: list[TriggerCondition] = field(default_factory=list)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)


def _resolve_field(path: str, data: dict[str, Any]) -> Any:
    """Resolve a dot-notation field path in a dict. Returns _MISSING if not found."""
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current
