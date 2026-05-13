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
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.conversational.confirm_manager")

# ─── Constants ────────────────────────────────────────────────

DEFAULT_TTL_SECONDS = 300  # 5 minutes
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_confirm_state.db",
)

# Status constants
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"


class ConfirmManager:
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
                conn.execute("""
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
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_confirmations_status
                    ON confirmations(status)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_confirmations_session
                    ON confirmations(session_id)
                """)
                conn.execute("""
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
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # ─── Public API: Confirmation Flow ─────────────────────────

    def request_confirmation(
        self,
        action_id: str,
        action_type: str,
        config: Dict,
        verdict: str,
        channel: str = "cli",
        session_id: str = "",
    ) -> Dict:
        """Create a confirmation request for a SafetyGate-flagged action.

        Args:
            action_id: Unique identifier for the action.
            action_type: Type of action (e.g., "database", "file_operation").
            config: Action configuration dict.
            verdict: SafetyGate verdict string (e.g., "CONFIRM").
            channel: Channel for user interaction (telegram, discord, web, cli).
            session_id: Session identifier for grouping.

        Returns:
            Confirmation request dict with message and metadata.
        """
        with self._lock:
            self._stats["total_requests"] += 1
            now = time.time()
            expires_at = now + self._ttl

            # Store in DB
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO confirmations
                       (action_id, action_type, config, verdict, status,
                        channel, session_id, required_role, created_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        action_id,
                        action_type,
                        json.dumps(config),
                        verdict,
                        STATUS_PENDING,
                        channel,
                        session_id,
                        "",
                        now,
                        expires_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            # Build the user-facing confirmation message
            message = self._format_confirm_message(action_type, config, verdict)

            logger.info(
                f"Confirmation requested: action_id={action_id}, "
                f"type={action_type}, verdict={verdict}, channel={channel}"
            )

            return {
                "action_id": action_id,
                "action_type": action_type,
                "verdict": verdict,
                "status": STATUS_PENDING,
                "message": message,
                "channel": channel,
                "expires_at": expires_at,
                "ttl_seconds": self._ttl,
                "options": ["yes", "no", "more_info"],
            }

    def process_response(
        self,
        action_id: str,
        user_response: str,
    ) -> Dict:
        """Handle user's yes/no/more_info response to a confirmation.

        Args:
            action_id: The action being confirmed.
            user_response: "yes", "no", or "more_info".

        Returns:
            Result dict with updated status and any follow-up info.
        """
        with self._lock:
            # Expire stale entries first
            self._expire_entries()

            # Look up the confirmation
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM confirmations WHERE action_id = ?",
                    (action_id,),
                ).fetchone()
            finally:
                conn.close()

            if row is None:
                return {
                    "status": "not_found",
                    "message": f"No pending confirmation for action {action_id}",
                }

            if row["status"] == STATUS_EXPIRED:
                return {
                    "status": "expired",
                    "message": "This confirmation request has expired. Please try again.",
                }

            if row["status"] != STATUS_PENDING:
                return {
                    "status": "already_resolved",
                    "message": f"Action {action_id} already has status: {row['status']}",
                    "current_status": row["status"],
                }

            # Check expiry (double-check in case _expire_entries missed it)
            if time.time() > row["expires_at"]:
                self._update_status(action_id, STATUS_EXPIRED)
                self._stats["total_expirations"] += 1
                return {
                    "status": "expired",
                    "message": "This confirmation request has expired. Please try again.",
                }

            response_lower = user_response.lower().strip()

            if response_lower in ("yes", "y", "confirm", "ok", "si", "sí"):
                # Confirm the action
                self._update_status(action_id, STATUS_CONFIRMED, responder_id="user")
                self._stats["total_confirmations"] += 1

                # Integrate with SafetyGate
                self._safety_gate_confirm(action_id)

                logger.info(f"Action {action_id} confirmed by user")

                return {
                    "status": STATUS_CONFIRMED,
                    "message": "Action confirmed. Proceeding with execution.",
                    "action_id": action_id,
                }

            elif response_lower in ("no", "n", "cancel", "deny", "rechazar"):
                # Deny the action
                self._update_status(action_id, STATUS_DENIED, responder_id="user")
                self._stats["total_denials"] += 1

                logger.info(f"Action {action_id} denied by user")

                return {
                    "status": STATUS_DENIED,
                    "message": "Action denied. The operation will not proceed.",
                    "action_id": action_id,
                }

            elif response_lower in ("more_info", "info", "details", "detalles"):
                # Return more info without changing status
                config = json.loads(row["config"]) if row["config"] else {}
                return {
                    "status": STATUS_PENDING,
                    "message": self._format_detailed_info(
                        row["action_type"], config, row["verdict"]
                    ),
                    "action_id": action_id,
                    "options": ["yes", "no"],
                }

            else:
                return {
                    "status": STATUS_PENDING,
                    "message": (
                        f"Unrecognized response '{user_response}'. "
                        f"Please reply with 'yes', 'no', or 'more_info'."
                    ),
                    "action_id": action_id,
                    "options": ["yes", "no", "more_info"],
                }

    # ─── Public API: Approval Flow ─────────────────────────────

    def request_approval(
        self,
        action_id: str,
        action_type: str,
        config: Dict,
        required_role: str,
        channel: str = "cli",
        session_id: str = "",
    ) -> Dict:
        """Create an approval request for role-based flow.

        Args:
            action_id: Unique identifier for the action.
            action_type: Type of action.
            config: Action configuration dict.
            required_role: Role required to approve (e.g., "admin", "finance_manager").
            channel: Channel for interaction.
            session_id: Session identifier.

        Returns:
            Approval request dict with message and metadata.
        """
        with self._lock:
            self._stats["total_requests"] += 1
            now = time.time()
            expires_at = now + self._ttl * 2  # Double TTL for approvals

            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO confirmations
                       (action_id, action_type, config, verdict, status,
                        channel, session_id, required_role, created_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        action_id,
                        action_type,
                        json.dumps(config),
                        "APPROVE",
                        STATUS_PENDING,
                        channel,
                        session_id,
                        required_role,
                        now,
                        expires_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            message = self._format_approve_message(action_type, config, required_role)

            logger.info(
                f"Approval requested: action_id={action_id}, "
                f"type={action_type}, required_role={required_role}"
            )

            return {
                "action_id": action_id,
                "action_type": action_type,
                "required_role": required_role,
                "status": STATUS_PENDING,
                "message": message,
                "channel": channel,
                "expires_at": expires_at,
                "ttl_seconds": self._ttl * 2,
            }

    def process_approval(
        self,
        action_id: str,
        approver_id: str,
        approved: bool,
        reason: str = "",
    ) -> Dict:
        """Handle approval response from a role-bearing approver.

        Args:
            action_id: The action being approved.
            approver_id: Identifier of the approver.
            approved: True if approved, False if denied.
            reason: Optional reason for the decision.

        Returns:
            Result dict with updated status.
        """
        with self._lock:
            self._expire_entries()

            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM confirmations WHERE action_id = ?",
                    (action_id,),
                ).fetchone()
            finally:
                conn.close()

            if row is None:
                return {
                    "status": "not_found",
                    "message": f"No pending approval for action {action_id}",
                }

            if row["status"] == STATUS_EXPIRED:
                return {
                    "status": "expired",
                    "message": "This approval request has expired.",
                }

            if row["status"] != STATUS_PENDING:
                return {
                    "status": "already_resolved",
                    "message": f"Action {action_id} already has status: {row['status']}",
                    "current_status": row["status"],
                }

            if time.time() > row["expires_at"]:
                self._update_status(action_id, STATUS_EXPIRED)
                self._stats["total_expirations"] += 1
                return {
                    "status": "expired",
                    "message": "This approval request has expired.",
                }

            if approved:
                self._update_status(
                    action_id, STATUS_APPROVED,
                    responder_id=approver_id,
                    reason=reason,
                )
                self._stats["total_approvals"] += 1

                # Integrate with SafetyGate
                required_role = row["required_role"] if "required_role" in row.keys() else ""
                self._safety_gate_approve(action_id, required_role)

                logger.info(f"Action {action_id} approved by {approver_id}")

                return {
                    "status": STATUS_APPROVED,
                    "message": "Action approved. Proceeding with execution.",
                    "action_id": action_id,
                    "approver_id": approver_id,
                }
            else:
                self._update_status(
                    action_id, STATUS_DENIED,
                    responder_id=approver_id,
                    reason=reason,
                )
                self._stats["total_denials"] += 1

                logger.info(f"Action {action_id} denied by {approver_id}: {reason}")

                return {
                    "status": STATUS_DENIED,
                    "message": f"Action denied by {approver_id}. Reason: {reason}",
                    "action_id": action_id,
                    "approver_id": approver_id,
                }

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
                    rows = conn.execute(
                        "SELECT * FROM confirmations WHERE status = ? AND session_id = ?",
                        (STATUS_PENDING, session_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
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
                row = conn.execute(
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

    # ─── Formatting ────────────────────────────────────────────

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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
            conn.execute(
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
            cursor = conn.execute(
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
            cursor = conn.execute(
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
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM confirmations WHERE status = ?",
                (STATUS_PENDING,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
