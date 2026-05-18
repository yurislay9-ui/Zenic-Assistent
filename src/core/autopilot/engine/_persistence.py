"""ZENIC-AGENTS - Autopilot Engine: Persistence Mixin

Provides schema initialization and engine-state persistence methods
for the AutopilotEngine class.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ._status import AutopilotStatus
from ._retry import _retry_operation

logger = logging.getLogger(__name__)


class _PersistenceMixin:
    """Mixin providing database schema and state persistence for AutopilotEngine."""

    # ── Schema ──────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create the engine state table if it does not exist."""
        if self._initialized:  # type: ignore[attr-defined]
            return
        with self._lock:  # type: ignore[attr-defined]
            if self._initialized:  # type: ignore[attr-defined]
                return

            db_path = self._db_path  # type: ignore[attr-defined]

            def _init() -> None:
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_autopilot_engine_state (
                            objective_id TEXT PRIMARY KEY,
                            status TEXT NOT NULL DEFAULT 'idle',
                            plan_id TEXT NOT NULL DEFAULT '',
                            last_cycle_at TEXT NOT NULL DEFAULT '',
                            last_cycle_result TEXT NOT NULL DEFAULT '{}',
                            cycle_count INTEGER NOT NULL DEFAULT 0
                        )
                    """)
                    conn.commit()
                finally:
                    conn.close()

            _retry_operation(_init)
            self._initialized = True  # type: ignore[attr-defined]
            logger.info("AutopilotEngine: Schema initialized at %s", db_path)

    # ── State Persistence ───────────────────────────────────

    def _persist_engine_state(
        self,
        objective_id: str,
        status: AutopilotStatus,
        plan_id: str = "",
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist the engine state for an objective.

        Args:
            objective_id: The objective ID.
            status: The current engine status.
            plan_id: The active plan ID.
            result: The latest cycle result.
        """
        self._ensure_schema()

        db_path = self._db_path  # type: ignore[attr-defined]
        cycle_count = self._cycle_count  # type: ignore[attr-defined]

        def _upsert() -> None:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT OR REPLACE INTO _zenic_autopilot_engine_state
                       (objective_id, status, plan_id, last_cycle_at,
                        last_cycle_result, cycle_count)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        objective_id,
                        status.value,
                        plan_id,
                        datetime.now(timezone.utc).isoformat(),
                        json.dumps(result or {}),
                        cycle_count,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        try:
            _retry_operation(_upsert)
        except Exception as exc:
            logger.warning(
                "AutopilotEngine: Failed to persist state for %s: %s",
                objective_id, exc,
            )
