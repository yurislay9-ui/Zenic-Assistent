"""Confirm Manager — Core mixin (request/approval flow)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from ._types import (
    DEFAULT_TTL_SECONDS,
    DEFAULT_DB_PATH,
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
)
from ._helpers import (
    _init_db, _get_conn, _update_status, _expire_entries,
    _format_confirm_message, _format_approve_message, _format_detailed_info,
    _safety_gate_confirm, _safety_gate_approve, cleanup,
)

logger = logging.getLogger("zenic_agents.conversational.confirm_manager")


class ConfirmManagerCoreMixin:
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
        self._lock = __import__("threading").RLock()
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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


