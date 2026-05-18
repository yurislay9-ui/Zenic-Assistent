"""
ZENIC-AGENTS — Confirm Manager Flow

Mixin with confirmation/approval flow methods, formatting functions,
and SafetyGate integration helpers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from ._types import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    STATUS_DENIED,
    STATUS_EXPIRED,
    STATUS_PENDING,
)

logger = logging.getLogger("zenic_agents.conversational.confirm_manager")


# ─── Formatting ────────────────────────────────────────────

def format_confirm_message(
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


def format_approve_message(
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


def format_detailed_info(
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


# ─── SafetyGate Integration ────────────────────────────────

def safety_gate_confirm(safety_gate: Any, action_id: str) -> None:
    """Integrate confirmation with SafetyGate."""
    if safety_gate is not None:
        try:
            if hasattr(safety_gate, 'confirm_action'):
                safety_gate.confirm_action(action_id)
                logger.debug(f"SafetyGate confirmed: {action_id}")
        except Exception as e:
            logger.warning(f"SafetyGate confirm_action failed: {e}")


def safety_gate_approve(safety_gate: Any, action_id: str, role: str) -> None:
    """Integrate approval with SafetyGate."""
    if safety_gate is not None:
        try:
            if hasattr(safety_gate, 'approve_action'):
                safety_gate.approve_action(action_id, role)
                logger.debug(f"SafetyGate approved: {action_id} by {role}")
        except Exception as e:
            logger.warning(f"SafetyGate approve_action failed: {e}")


# ─── Flow Mixin ────────────────────────────────────────────

class ConfirmFlowMixin:
    """Mixin providing confirmation/approval flow methods for ConfirmManager.

    Expects the host class to provide:
      - _lock: threading.RLock
      - _ttl: int
      - _stats: dict
      - _safety_gate: Any
      - _get_conn() -> sqlite3.Connection
      - _update_status(action_id, status, responder_id, reason) -> None
      - _expire_entries() -> None
    """

    # ─── Confirmation Flow ─────────────────────────────────────

    def request_confirmation(
        self,
        action_id: str,
        action_type: str,
        config: Dict,
        verdict: str,
        channel: str = "cli",
        session_id: str = "",
    ) -> Dict:
        """Create a confirmation request for a SafetyGate-flagged action."""
        with self._lock:  # type: ignore[attr-defined]
            self._stats["total_requests"] += 1  # type: ignore[attr-defined]
            now = time.time()
            expires_at = now + self._ttl  # type: ignore[attr-defined]

            # Store in DB
            conn = self._get_conn()  # type: ignore[attr-defined]
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
            message = format_confirm_message(action_type, config, verdict)

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
                "ttl_seconds": self._ttl,  # type: ignore[attr-defined]
                "options": ["yes", "no", "more_info"],
            }

    def process_response(
        self,
        action_id: str,
        user_response: str,
    ) -> Dict:
        """Handle user's yes/no/more_info response to a confirmation."""
        with self._lock:  # type: ignore[attr-defined]
            # Expire stale entries first
            self._expire_entries()  # type: ignore[attr-defined]

            # Look up the confirmation
            conn = self._get_conn()  # type: ignore[attr-defined]
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
                self._update_status(action_id, STATUS_EXPIRED)  # type: ignore[attr-defined]
                self._stats["total_expirations"] += 1  # type: ignore[attr-defined]
                return {
                    "status": "expired",
                    "message": "This confirmation request has expired. Please try again.",
                }

            response_lower = user_response.lower().strip()

            if response_lower in ("yes", "y", "confirm", "ok", "si", "sí"):
                # Confirm the action
                self._update_status(action_id, STATUS_CONFIRMED, responder_id="user")  # type: ignore[attr-defined]
                self._stats["total_confirmations"] += 1  # type: ignore[attr-defined]

                # Integrate with SafetyGate
                safety_gate_confirm(self._safety_gate, action_id)  # type: ignore[attr-defined]

                logger.info(f"Action {action_id} confirmed by user")

                return {
                    "status": STATUS_CONFIRMED,
                    "message": "Action confirmed. Proceeding with execution.",
                    "action_id": action_id,
                }

            elif response_lower in ("no", "n", "cancel", "deny", "rechazar"):
                # Deny the action
                self._update_status(action_id, STATUS_DENIED, responder_id="user")  # type: ignore[attr-defined]
                self._stats["total_denials"] += 1  # type: ignore[attr-defined]

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
                    "message": format_detailed_info(
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

    # ─── Approval Flow ─────────────────────────────────────────

    def request_approval(
        self,
        action_id: str,
        action_type: str,
        config: Dict,
        required_role: str,
        channel: str = "cli",
        session_id: str = "",
    ) -> Dict:
        """Create an approval request for role-based flow."""
        with self._lock:  # type: ignore[attr-defined]
            self._stats["total_requests"] += 1  # type: ignore[attr-defined]
            now = time.time()
            expires_at = now + self._ttl * 2  # type: ignore[attr-defined]

            conn = self._get_conn()  # type: ignore[attr-defined]
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

            message = format_approve_message(action_type, config, required_role)

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
                "ttl_seconds": self._ttl * 2,  # type: ignore[attr-defined]
            }

    def process_approval(
        self,
        action_id: str,
        approver_id: str,
        approved: bool,
        reason: str = "",
    ) -> Dict:
        """Handle approval response from a role-bearing approver."""
        with self._lock:  # type: ignore[attr-defined]
            self._expire_entries()  # type: ignore[attr-defined]

            conn = self._get_conn()  # type: ignore[attr-defined]
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
                self._update_status(action_id, STATUS_EXPIRED)  # type: ignore[attr-defined]
                self._stats["total_expirations"] += 1  # type: ignore[attr-defined]
                return {
                    "status": "expired",
                    "message": "This approval request has expired.",
                }

            if approved:
                self._update_status(  # type: ignore[attr-defined]
                    action_id, STATUS_APPROVED,
                    responder_id=approver_id,
                    reason=reason,
                )
                self._stats["total_approvals"] += 1  # type: ignore[attr-defined]

                # Integrate with SafetyGate
                required_role = row["required_role"] if "required_role" in row.keys() else ""
                safety_gate_approve(self._safety_gate, action_id, required_role)  # type: ignore[attr-defined]

                logger.info(f"Action {action_id} approved by {approver_id}")

                return {
                    "status": STATUS_APPROVED,
                    "message": "Action approved. Proceeding with execution.",
                    "action_id": action_id,
                    "approver_id": approver_id,
                }
            else:
                self._update_status(  # type: ignore[attr-defined]
                    action_id, STATUS_DENIED,
                    responder_id=approver_id,
                    reason=reason,
                )
                self._stats["total_denials"] += 1  # type: ignore[attr-defined]

                logger.info(f"Action {action_id} denied by {approver_id}: {reason}")

                return {
                    "status": STATUS_DENIED,
                    "message": f"Action denied by {approver_id}. Reason: {reason}",
                    "action_id": action_id,
                    "approver_id": approver_id,
                }
