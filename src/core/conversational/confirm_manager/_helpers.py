"""Confirm Manager — Helper methods (DB, formatting, integration)."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from ._types import (
    DEFAULT_TTL_SECONDS,
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
)

logger = logging.getLogger("zenic_agents.conversational.confirm_manager")

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

    # ─── Public API: Confirmation Flow ─────────────────────────


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


    def _format_confirm_message(
        action_type: str,
        config: Dict,
        verdict: str,
    ) -> str:
        """Format user-facing confirmation request message."""
        lines = [
            "⚠️ **Confirmation Required**",
            "",
            f"**Action Type:** {action_type}",
            f"**Safety Verdict:** {verdict}",
        ]

        # Add relevant config details
        if config:
            lines.append("")
            lines.append("**Details:**")
            for key, value in list(config.items())[:8]:  # Limit displayed fields
                val_str = str(value)[:100]
                lines.append(f"  • {key}: {val_str}")

        lines.extend([
            "",
            "Do you want to proceed?",
            "  • Reply **yes** to confirm",
            "  • Reply **no** to deny",
            "  • Reply **more_info** for details",
        ])

        return "\n".join(lines)


    def _format_approve_message(
        action_type: str,
        config: Dict,
        required_role: str,
    ) -> str:
        """Format approval request message."""
        lines = [
            "🔒 **Approval Required**",
            "",
            f"**Action Type:** {action_type}",
            f"**Required Role:** {required_role}",
        ]

        if config:
            lines.append("")
            lines.append("**Details:**")
            for key, value in list(config.items())[:8]:
                val_str = str(value)[:100]
                lines.append(f"  • {key}: {val_str}")

        lines.extend([
            "",
            f"This action requires approval from a user with the **{required_role}** role.",
        ])

        return "\n".join(lines)


    def _format_detailed_info(
        action_type: str,
        config: Dict,
        verdict: str,
    ) -> str:
        """Format detailed information about a pending action."""
        lines = [
            "📋 **Action Details**",
            "",
            f"**Type:** {action_type}",
            f"**Verdict:** {verdict}",
        ]

        if config:
            lines.append("")
            lines.append("**Full Configuration:**")
            config_str = json.dumps(config, indent=2, ensure_ascii=False)
            # Truncate if too long
            if len(config_str) > 1000:
                config_str = config_str[:1000] + "\n... (truncated)"
            lines.append(f"```json\n{config_str}\n```")

        lines.extend([
            "",
            "Do you want to proceed? (yes/no)",
        ])

        return "\n".join(lines)

    # ─── Internal Helpers ──────────────────────────────────────


    def _safety_gate_confirm(self, action_id: str) -> None:
        """Integrate confirmation with SafetyGate."""
        if self._safety_gate is not None:
            try:
                if hasattr(self._safety_gate, 'confirm_action'):
                    self._safety_gate.confirm_action(action_id)
                    logger.debug(f"SafetyGate confirmed: {action_id}")
            except Exception as e:
                logger.warning(f"SafetyGate confirm_action failed: {e}")


    def _safety_gate_approve(self, action_id: str, role: str) -> None:
        """Integrate approval with SafetyGate."""
        if self._safety_gate is not None:
            try:
                if hasattr(self._safety_gate, 'approve_action'):
                    self._safety_gate.approve_action(action_id, role)
                    logger.debug(f"SafetyGate approved: {action_id} by {role}")
            except Exception as e:
                logger.warning(f"SafetyGate approve_action failed: {e}")

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

