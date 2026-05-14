"""
ZENIC-AGENTS — TriggerMap (B1: Event-driven Actions Engine)

Declarative mapping from event patterns to automation IDs.
Supports wildcard matching (fnmatch), condition filtering,
priority-based sorting, YAML/dict bulk loading, and SQLite persistence.

Usage:
    tmap = TriggerMap()
    tid = tmap.register("db.*", "auto_stock_alert", priority=5,
                         condition={"field": "value", "operator": "lt", "value": 10})
    matches = tmap.lookup("db.stock_below", {"entity_id": "AAPL", "value": 5.0})
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("zenic_agents.events.trigger_map")

DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
DB_PATH = os.path.join(DB_DIR, "trigger_map.sqlite")


# ─── Dataclasses ────────────────────────────────────────────────

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


# ─── Sentinel for missing fields ────────────────────────────────

_MISSING = object()


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


# ─── TriggerMap ─────────────────────────────────────────────────

class TriggerMap:
    """
    Declarative mapping from events to automations.

    Thread-safe with RLock. Persisted to SQLite.
    Singleton pattern via get_trigger_map() / reset_trigger_map().
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or DB_PATH
        self._mappings: dict[str, TriggerMapping] = {}
        self._initialized = False
        self._init_db()
        self._load_from_db()

    # ── DB Setup ────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize the SQLite database and create table if needed."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trigger_mappings (
                    trigger_id    TEXT PRIMARY KEY,
                    event_pattern TEXT NOT NULL,
                    automation_id TEXT NOT NULL,
                    priority      INTEGER NOT NULL DEFAULT 0,
                    condition_json TEXT NOT NULL DEFAULT '[]',
                    enabled       INTEGER NOT NULL DEFAULT 1,
                    created_at    REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_pattern
                ON trigger_mappings(event_pattern)
            """)
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def _load_from_db(self) -> None:
        """Load all mappings from SQLite into memory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM trigger_mappings"
            ).fetchall()
            with self._lock:
                for row in rows:
                    mapping = _mapping_from_row(row)
                    self._mappings[mapping.trigger_id] = mapping
        finally:
            conn.close()
        logger.info(
            "TriggerMap: loaded %d mappings from %s",
            len(self._mappings), self._db_path,
        )

    # ── Register ────────────────────────────────────────────────

    def register(
        self,
        event_pattern: str,
        automation_id: str,
        priority: int = 0,
        condition: dict[str, Any] | None = None,
    ) -> str:
        """
        Register a trigger mapping.

        Args:
            event_pattern: Wildcard pattern for event types (e.g. "db.*").
            automation_id: Automation to invoke when matched.
            priority: Higher = fires first when multiple matches.
            condition: Optional condition dict with keys:
                       {"field": ..., "operator": ..., "value": ...}

        Returns:
            trigger_id (unique string).
        """
        if not event_pattern or not isinstance(event_pattern, str):
            raise ValueError("event_pattern must be a non-empty string")
        if not automation_id or not isinstance(automation_id, str):
            raise ValueError("automation_id must be a non-empty string")

        trigger_id = f"trg_{uuid.uuid4().hex[:12]}"

        conditions: list[TriggerCondition] = []
        if condition:
            conditions.append(_condition_from_dict(condition))

        mapping = TriggerMapping(
            trigger_id=trigger_id,
            event_pattern=event_pattern,
            automation_id=automation_id,
            priority=priority,
            condition=conditions,
            enabled=True,
            created_at=time.time(),
        )

        condition_json = json.dumps([_condition_to_dict(c) for c in conditions])

        with self._lock:
            self._mappings[trigger_id] = mapping
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO trigger_mappings
                        (trigger_id, event_pattern, automation_id, priority,
                         condition_json, enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trigger_id,
                        event_pattern,
                        automation_id,
                        priority,
                        condition_json,
                        1,
                        mapping.created_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(
            "TriggerMap: registered %s → %s (pattern=%s, priority=%d)",
            trigger_id, automation_id, event_pattern, priority,
        )
        return trigger_id

    # ── Unregister ──────────────────────────────────────────────

    def unregister(self, trigger_id: str) -> bool:
        """
        Unregister a trigger mapping.

        Returns:
            True if found and removed, False otherwise.
        """
        with self._lock:
            mapping = self._mappings.pop(trigger_id, None)
            if mapping is None:
                return False
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    "DELETE FROM trigger_mappings WHERE trigger_id = ?",
                    (trigger_id,),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info("TriggerMap: unregistered %s", trigger_id)
        return True

    # ── Lookup ──────────────────────────────────────────────────

    def lookup(
        self,
        event_type: str,
        event_data: dict[str, Any] | None = None,
    ) -> list[TriggerMapping]:
        """
        Find all automations that should fire for a given event.

        Matches event_type against registered patterns, then filters
        by conditions. Results are sorted by priority (descending).

        Args:
            event_type: The concrete event type (e.g. "db.stock_below").
            event_data: Optional event payload for condition evaluation.

        Returns:
            List of matching TriggerMapping objects, sorted by priority desc.
        """
        event_data = event_data or {}
        matches: list[TriggerMapping] = []

        with self._lock:
            for mapping in self._mappings.values():
                if not mapping.enabled:
                    continue
                if not _match_event_pattern(mapping.event_pattern, event_type):
                    continue
                # Evaluate all conditions
                all_pass = True
                for cond in mapping.condition:
                    if not cond.evaluate(event_data):
                        all_pass = False
                        break
                if all_pass:
                    matches.append(mapping)

        # Sort by priority descending (highest first)
        matches.sort(key=lambda m: m.priority, reverse=True)
        return matches

    # ── Bulk Load ───────────────────────────────────────────────

    def load_from_yaml(self, yaml_path: str) -> int:
        """
        Bulk load mappings from a YAML file.

        Expected YAML format:
            mappings:
              - event_pattern: "db.*"
                automation_id: "auto_stock"
                priority: 5
                condition:
                  field: "value"
                  operator: "lt"
                  value: 10

        Returns:
            Number of mappings loaded.
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logger.error(
                "TriggerMap: PyYAML not installed, cannot load from YAML. "
                "Install with: pip install pyyaml"
            )
            return 0

        try:
            with open(yaml_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            logger.error("TriggerMap: failed to load YAML from %s: %s", yaml_path, exc)
            return 0

        if not isinstance(data, dict):
            logger.error("TriggerMap: YAML root must be a dict with 'mappings' key")
            return 0

        raw_mappings = data.get("mappings", [])
        if not isinstance(raw_mappings, list):
            logger.error("TriggerMap: 'mappings' key must be a list")
            return 0

        return self.load_from_dict(raw_mappings)

    def load_from_dict(self, mappings: list[dict[str, Any]]) -> int:
        """
        Bulk load mappings from a list of dicts.

        Each dict must have at least 'event_pattern' and 'automation_id'.

        Returns:
            Number of mappings loaded.
        """
        count = 0
        for m in mappings:
            try:
                event_pattern = m.get("event_pattern", "")
                automation_id = m.get("automation_id", "")
                priority = m.get("priority", 0)
                condition = m.get("condition")
                if not event_pattern or not automation_id:
                    logger.warning(
                        "TriggerMap: skipping mapping with missing "
                        "event_pattern or automation_id: %s", m,
                    )
                    continue
                self.register(
                    event_pattern=event_pattern,
                    automation_id=automation_id,
                    priority=priority,
                    condition=condition,
                )
                count += 1
            except Exception as exc:
                logger.warning(
                    "TriggerMap: failed to load mapping %s: %s", m, exc,
                )
        logger.info("TriggerMap: loaded %d mappings from dict", count)
        return count

    # ── List ────────────────────────────────────────────────────

    def list_mappings(
        self,
        event_pattern: str | None = None,
    ) -> list[TriggerMapping]:
        """
        List registered mappings, optionally filtered by event_pattern.

        Args:
            event_pattern: If provided, only return mappings whose pattern
                           matches exactly or via wildcard.

        Returns:
            List of TriggerMapping objects.
        """
        with self._lock:
            result = list(self._mappings.values())

        if event_pattern is not None:
            result = [
                m for m in result
                if m.event_pattern == event_pattern
                or fnmatch.fnmatch(m.event_pattern, event_pattern)
            ]

        result.sort(key=lambda m: (m.event_pattern, -m.priority))
        return result


# ─── Singleton ──────────────────────────────────────────────────

_instance: TriggerMap | None = None
_instance_lock = threading.Lock()


def get_trigger_map() -> TriggerMap:
    """Return the singleton TriggerMap instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TriggerMap()
    return _instance


def reset_trigger_map() -> None:
    """Reset the singleton (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None


__all__ = [
    "TriggerMap",
    "TriggerMapping",
    "TriggerCondition",
    "ConditionOperator",
    "get_trigger_map",
    "reset_trigger_map",
]
