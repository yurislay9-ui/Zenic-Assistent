"""
Zenic-Agents Asistente - Degradation Persistence Layer (Phase 6.4)

SQLite-backed persistence for degradation state and transition history.
Extracted from manager.py for the 400-line limit.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from .types import DegradationLevel, DegradationReason, DegradationState

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS degradation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    level INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT 'none',
    message TEXT NOT NULL DEFAULT '',
    entered_at REAL NOT NULL DEFAULT 0.0,
    restricted_features TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS degradation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_level INTEGER NOT NULL,
    to_level INTEGER NOT NULL,
    reason TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL,
    operator TEXT NOT NULL DEFAULT 'system',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
);
"""


class DegradationPersistence:
    """SQLite-backed persistence for degradation state and history.

    Uses a single persistent connection so that ``:memory:`` databases
    work correctly.  All access is serialized through an internal lock
    for thread safety.
    """

    def __init__(self, db_path: str = "degraded_mode.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Connection management ─────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    # ── Schema bootstrap ──────────────────────────────────

    def _init_db(self) -> None:
        with self._lock:
            try:
                conn = self._get_conn()
                conn.executescript(_SCHEMA)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, ?)",
                    (_SCHEMA_VERSION,),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO degradation_state "
                    "(id, level, reason, message, entered_at, updated_at) "
                    "VALUES (1, 0, 'none', '', 0.0, ?)",
                    (time.time(),),
                )
                conn.commit()
            except Exception as exc:
                logger.error("DegradationPersistence: DB init failed: %s", exc)

    # ── State CRUD ────────────────────────────────────────

    def load_state(self) -> DegradationState:
        """Load the current degradation state from the database."""
        with self._lock:
            try:
                conn = self._get_conn()
                row = conn.execute(
                    "SELECT * FROM degradation_state WHERE id = 1"
                ).fetchone()
                if row:
                    return DegradationState(
                        level=DegradationLevel(row["level"]),
                        reason=DegradationReason(row["reason"]),
                        message=row["message"] or "",
                        entered_at=row["entered_at"] or 0.0,
                        restricted_features=json.loads(
                            row["restricted_features"] or "[]"),
                        metadata=json.loads(row["metadata"] or "{}"),
                    )
            except Exception as exc:
                logger.error("DegradationPersistence: load_state failed: %s", exc)
        return DegradationState()

    def save_state(self, state: DegradationState) -> None:
        """Persist the current degradation state."""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "UPDATE degradation_state SET "
                    "level=?, reason=?, message=?, entered_at=?, "
                    "restricted_features=?, metadata=?, updated_at=? "
                    "WHERE id=1",
                    (
                        state.level.value,
                        state.reason.value,
                        state.message,
                        state.entered_at,
                        json.dumps(state.restricted_features),
                        json.dumps(state.metadata),
                        time.time(),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.error("DegradationPersistence: save_state failed: %s", exc)

    # ── History ───────────────────────────────────────────

    def append_history(
        self,
        from_level: DegradationLevel,
        to_level: DegradationLevel,
        reason: DegradationReason,
        message: str = "",
        operator: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a degradation transition in the history table."""
        with self._lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO degradation_history "
                    "(from_level, to_level, reason, message, "
                    "timestamp, operator, metadata) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        from_level.value,
                        to_level.value,
                        reason.value,
                        message,
                        time.time(),
                        operator,
                        json.dumps(metadata or {}),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.error(
                    "DegradationPersistence: append_history failed: %s", exc)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent degradation transition records."""
        with self._lock:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT * FROM degradation_history "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            except Exception as exc:
                logger.error(
                    "DegradationPersistence: get_history failed: %s", exc)
                return []

    # ── Maintenance ───────────────────────────────────────

    def purge_history(self, older_than_days: int = 90) -> int:
        """Delete history records older than *older_than_days* days."""
        cutoff = time.time() - (older_than_days * 86400)
        with self._lock:
            try:
                conn = self._get_conn()
                cur = conn.execute(
                    "DELETE FROM degradation_history WHERE timestamp < ?",
                    (cutoff,),
                )
                conn.commit()
                return cur.rowcount
            except Exception as exc:
                logger.error(
                    "DegradationPersistence: purge_history failed: %s", exc)
                return 0

    def close(self) -> None:
        """Close the persistent database connection."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
