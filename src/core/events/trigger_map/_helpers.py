"""Helpers for trigger_map."""

from __future__ import annotations

import fnmatch
import json
import logging
import sqlite3
import time
from typing import Any

from ._types import (
    _MISSING,
    _resolve_field,
    ConditionOperator,
    TriggerCondition,
    TriggerMapping,
)

logger = logging.getLogger("zenic_agents.events.trigger_map")


def _match_event_pattern(pattern: str, event_type: str) -> bool:
    """
    Match an event_type against a pattern.

    Rules:
      - "db.*" matches "db.stock_below" (one segment after db.)
      - "sna.**" matches "sna.stock.below" (any depth after sna.)
      - Exact match if no wildcards.
      - Standard fnmatch for single-level wildcards (* and ?).
    """
    if pattern == event_type:
        return True

    # Handle recursive wildcard **
    if "**" in pattern:
        # "prefix.**" matches "prefix.any.thing.here"
        # and also matches "prefix" itself
        prefix = pattern.replace(".**", "").replace("**", "")
        if not prefix:
            return True  # "**" matches everything
        if event_type == prefix:
            return True
        if event_type.startswith(prefix + "."):
            return True
        return False

    # Standard fnmatch for single-level wildcards
    return fnmatch.fnmatch(event_type, pattern)


def _condition_from_dict(d: dict[str, Any]) -> TriggerCondition:
    """Build a TriggerCondition from a dict."""
    return TriggerCondition(
        field=d["field"],
        operator=ConditionOperator(d.get("operator", "eq")),
        value=d.get("value"),
    )


def _condition_to_dict(c: TriggerCondition) -> dict[str, Any]:
    """Serialize a TriggerCondition to a dict."""
    return {
        "field": c.field,
        "operator": c.operator.value,
        "value": c.value,
    }


def _mapping_from_row(row: sqlite3.Row) -> TriggerMapping:
    """Deserialize a TriggerMapping from a SQLite row."""
    condition_raw = row["condition_json"]
    conditions: list[TriggerCondition] = []
    if condition_raw:
        try:
            cond_list = json.loads(condition_raw)
            conditions = [_condition_from_dict(cd) for cd in cond_list]
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning(
                "TriggerMap: failed to parse condition for trigger_id=%s",
                row["trigger_id"],
            )

    return TriggerMapping(
        trigger_id=row["trigger_id"],
        event_pattern=row["event_pattern"],
        automation_id=row["automation_id"],
        priority=row["priority"],
        condition=conditions,
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )
