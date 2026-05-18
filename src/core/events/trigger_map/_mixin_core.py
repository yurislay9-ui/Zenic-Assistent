"""Core logic for trigger_map."""

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
from typing import Any
from ._types import *
from ._helpers import *

logger = logging.getLogger("zenic_agents.events.trigger_map")

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
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
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
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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

