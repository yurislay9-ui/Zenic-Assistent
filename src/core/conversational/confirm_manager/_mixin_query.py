"""Confirm Manager — Query mixin (process_approval, get_pending, cancel, stats)."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from ._types import (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
)
from ._helpers import _get_conn, _update_status, _expire_entries


class ConfirmManagerQueryMixin:
    """Query, approval processing, and cancellation methods for ConfirmManager."""

    # ─── Public API: Approval Processing ────────────────────────

    def process_approval(
        self,
        action_id: str,
        approver_id: str,
        approved: bool,
        reason: str = "",
    ) -> Dict:
        """Handle approval response from a role-bearing approver."""
        with self._lock:
            self._expire_entries()

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
                self._update_status(action_id, STATUS_APPROVED, responder_id=approver_id, reason=reason)
                self._stats["total_approvals"] += 1
                required_role = row["required_role"] if "required_role" in row.keys() else ""
                self._safety_gate_approve(action_id, required_role)
                __import__("logging").getLogger("zenic_agents.conversational.confirm_manager").info(
                    f"Action {action_id} approved by {approver_id}"
                )
                return {
                    "status": STATUS_APPROVED,
                    "message": "Action approved. Proceeding with execution.",
                    "action_id": action_id, "approver_id": approver_id,
                }
            else:
                self._update_status(action_id, STATUS_DENIED, responder_id=approver_id, reason=reason)
                self._stats["total_denials"] += 1
                __import__("logging").getLogger("zenic_agents.conversational.confirm_manager").info(
                    f"Action {action_id} denied by {approver_id}: {reason}"
                )
                return {
                    "status": STATUS_DENIED,
                    "message": f"Action denied by {approver_id}. Reason: {reason}",
                    "action_id": action_id, "approver_id": approver_id,
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

            __import__("logging").getLogger("zenic_agents.conversational.confirm_manager").info(
                f"Action {action_id} cancelled"
            )
            return True

    # ─── Formatting ────────────────────────────────────────────

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
