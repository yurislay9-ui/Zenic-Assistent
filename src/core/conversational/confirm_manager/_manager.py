"""
Confirm Manager — Handles confirmation/approval flow for SafetyGate-flagged actions.

When the SafetyGate returns CONFIRM or APPROVE verdicts, this manager
creates user-facing confirmation requests, tracks their state, and
integrates with the SafetyGate's confirm_action() / approve_action()
methods upon user response.

Persistence: SQLite with TTL (auto-expire after configurable timeout).
Thread safety: RLock for all state mutations.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ._flow import ConfirmFlowMixin
from ._types import (
    DEFAULT_DB_PATH,
    DEFAULT_TTL_SECONDS,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_PENDING,
)

logger = logging.getLogger("zenic_agents.conversational.confirm_manager")


class ConfirmManager(ConfirmFlowMixin):
    """Manages confirmation/approval flow for SafetyGate-flagged actions.

    Thread-safe. SQLite-backed with TTL auto-expiry.
    Integrates with SafetyGate.confirm_action() and SafetyGate.approve_action().
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        safety_gate: Optional[Any] = None,
    ) -> None:
        """
        Args:
            db_path: Path to SQLite database for persistence.
                     If None, uses default path next to this module.
            ttl_seconds: Time-to-live for pending confirmations (seconds).
            safety_gate: SafetyGate instance for confirm/approve integration.
                         If None, SafetyGate integration is disabled.
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._ttl = ttl_seconds
        self._safety_gate = safety_gate
        self._lock = threading.RLock()
        self._stats = {
            "total_requests": 0,
            "total_confirmations": 0,
            "total_approvals": 0,
            "total_denials": 0,
            "total_cancellations": 0,
            "total_expirations": 0,
        }

        # Initialize DB
        self._init_db()

    # ─── Database ──────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize the SQLite database schema."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE TABLE IF NOT EXISTS confirmations (
                        action_id TEXT PRIMARY KEY,
                        action_type TEXT NOT NULL,
                        config TEXT NOT NULL DEFAULT '{}',
                        verdict TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'pending',
                        channel TEXT NOT NULL DEFAULT '',
                        session_id TEXT NOT NULL DEFAULT '',
                        required_role TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        responded_at REAL,
                        responder_id TEXT,
                        response_reason TEXT,
                        extra TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE INDEX IF NOT EXISTS idx_confirmations_status
                    ON confirmations(status)
                """)
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE INDEX IF NOT EXISTS idx_confirmations_session
                    ON confirmations(session_id)
                """)
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE INDEX IF NOT EXISTS idx_confirmations_expires
                    ON confirmations(expires_at)
                """)
                conn.commit()
            finally:
                conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection (one per thread)."""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("PRAGMA busy_timeout=5000")  # nosemgrep: sqlalchemy-execute-raw-query
        return conn

    # ─── Public API: Query ─────────────────────────────────────

    def get_pending(self, session_id: str = "") -> List[Dict]:
        """Return pending confirmations for a session.

        Args:
            session_id: If provided, filter by session. If empty, return all pending.

        Returns:
            List of pending confirmation dicts.
        """
        with self._lock:
            self._expire_entries()

            conn = self._get_conn()
            try:
                if session_id:
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM confirmations WHERE status = ? AND session_id = ?",
                        (STATUS_PENDING, session_id),
                    ).fetchall()
                else:
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM confirmations WHERE status = ?",
                        (STATUS_PENDING,),
                    ).fetchall()
            finally:
                conn.close()

            results: List[Dict] = []
            for row in rows:
                config = json.loads(row["config"]) if row["config"] else {}
                results.append({
                    "action_id": row["action_id"],
                    "action_type": row["action_type"],
                    "config": config,
                    "verdict": row["verdict"],
                    "status": row["status"],
                    "channel": row["channel"],
                    "session_id": row["session_id"],
                    "required_role": row["required_role"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "ttl_remaining": max(0, row["expires_at"] - time.time()),
                })

            return results

    def cancel(self, action_id: str) -> bool:
        """Cancel a pending confirmation.

        Args:
            action_id: The action to cancel.

        Returns:
            True if successfully cancelled, False if not found or not pending.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT status FROM confirmations WHERE action_id = ?",
                    (action_id,),
                ).fetchone()
            finally:
                conn.close()

            if row is None or row["status"] != STATUS_PENDING:
                return False

            self._update_status(action_id, STATUS_CANCELLED)
            self._stats["total_cancellations"] += 1

            logger.info(f"Action {action_id} cancelled")
            return True

    # ─── Internal Helpers ──────────────────────────────────────

    def _update_status(
        self,
        action_id: str,
        status: str,
        responder_id: str = "",
        reason: str = "",
    ) -> None:
        """Update the status of a confirmation in the database."""
        conn = self._get_conn()
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """UPDATE confirmations
                   SET status = ?, responded_at = ?, responder_id = ?, response_reason = ?
                   WHERE action_id = ?""",
                (status, time.time(), responder_id, reason, action_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _expire_entries(self) -> None:
        """Mark expired entries as expired."""
        now = time.time()
        conn = self._get_conn()
        try:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "UPDATE confirmations SET status = ? WHERE status = ? AND expires_at < ?",
                (STATUS_EXPIRED, STATUS_PENDING, now),
            )
            expired_count = cursor.rowcount
            conn.commit()
            if expired_count > 0:
                self._stats["total_expirations"] += expired_count
                logger.debug(f"Expired {expired_count} confirmation(s)")
        finally:
            conn.close()

    # ─── Cleanup ───────────────────────────────────────────────

    def cleanup(self, max_age_hours: int = 24) -> int:
        """Remove old resolved/expired entries from the database.

        Args:
            max_age_hours: Maximum age of non-pending entries to keep.

        Returns:
            Number of entries removed.
        """
        cutoff = time.time() - (max_age_hours * 3600)

        conn = self._get_conn()
        try:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """DELETE FROM confirmations
                   WHERE status != ? AND responded_at < ?""",
                (STATUS_PENDING, cutoff),
            )
            removed = cursor.rowcount
            conn.commit()
            if removed > 0:
                logger.info(f"Cleaned up {removed} old confirmation(s)")
            return removed
        finally:
            conn.close()

    # ─── Properties ────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Manager statistics."""
        with self._lock:
            return {**self._stats}

    @property
    def pending_count(self) -> int:
        """Number of currently pending confirmations."""
        conn = self._get_conn()
        try:
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) as cnt FROM confirmations WHERE status = ?",
                (STATUS_PENDING,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
