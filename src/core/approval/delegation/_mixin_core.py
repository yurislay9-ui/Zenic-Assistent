"""
Delegation Manager — Core Mixin.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ._types import DelegationRule, DelegationRecord
from ._mixin_persistence import DelegationPersistenceMixin

logger = logging.getLogger(__name__)


class DelegationManager(DelegationPersistenceMixin):
    """Manages approval delegation rules and records.

    When a primary approver is unavailable, their authority can be
    temporarily delegated to another user with a sufficient role.
    """

    def __init__(
        self,
        db_path: str = "delegation.sqlite",
        default_timeout_hours: int = 24,
    ) -> None:
        self._db_path = db_path
        self._default_timeout_hours = default_timeout_hours
        import threading
        self._lock = threading.RLock()
        self._init_db()

    # ── Core Operations ────────────────────────────────────

    def create_delegation(
        self,
        from_user_id: int,
        to_user_id: int,
        from_role: str,
        to_role: str,
        expires_hours: int = 0,
        reason: str = "",
    ) -> DelegationRule:
        """Create a new delegation rule."""
        hours = expires_hours if expires_hours > 0 else self._default_timeout_hours
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=hours)).isoformat()

        rule = DelegationRule(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            from_role=from_role,
            to_role=to_role,
            active=True,
            expires_at=expires_at,
            reason=reason,
        )

        with self._lock:
            self._persist_rule(rule, insert=True)

        logger.info(
            "DelegationManager: Created rule %s — user %d (%s) → user %d (%s) "
            "expires=%s reason='%s'",
            rule.rule_id, from_user_id, from_role, to_user_id, to_role,
            expires_at, reason[:50],
        )
        return rule

    def revoke_delegation(self, rule_id: str) -> bool:
        """Revoke (deactivate) a delegation rule."""
        with self._lock:
            rule = self._find_rule(rule_id)
            if rule is None:
                logger.warning("DelegationManager: Rule %s not found for revocation", rule_id)
                return False
            rule.active = False
            self._persist_rule(rule, insert=False)

        logger.info("DelegationManager: Revoked rule %s", rule_id)
        return True

    def find_delegate(self, user_id: int, role: str) -> Optional[int]:
        """Find an active delegate for the given user+role combination."""
        from src.core.auth_service import ROLE_HIERARCHY

        with self._lock:
            rules = self._list_active_rules_for(user_id, role)

        for rule in rules:
            to_level = ROLE_HIERARCHY.get(rule.to_role, -1)
            from_level = ROLE_HIERARCHY.get(rule.from_role, -1)
            if to_level >= from_level:
                return rule.to_user_id
            logger.warning(
                "DelegationManager: Delegate user %d has role '%s' (level %d) "
                "insufficient for delegator role '%s' (level %d) — skipping",
                rule.to_user_id, rule.to_role, to_level,
                rule.from_role, from_level,
            )

        return None

    def acknowledge_delegation(self, record_id: str) -> bool:
        """Acknowledge a delegation record."""
        with self._lock:
            record = self._find_record(record_id)
            if record is None:
                logger.warning("DelegationManager: Record %s not found", record_id)
                return False
            record.acknowledged = True
            self._persist_record(record, insert=False)

        logger.info("DelegationManager: Acknowledged record %s", record_id)
        return True

    def auto_delegate_pending(
        self, request_id: str, timeout_hours: int = 2,
    ) -> Optional[int]:
        """If an approval request is pending beyond *timeout_hours*, auto-delegate."""
        from ..chain import get_approval_chain

        chain = get_approval_chain()
        request = chain.get_request(request_id)
        if request is None:
            logger.warning("DelegationManager: Request %s not found", request_id)
            return None

        if request.status.value != "pending":
            logger.info(
                "DelegationManager: Request %s is not pending (status=%s)",
                request_id, request.status.value,
            )
            return None

        created = datetime.fromisoformat(request.created_at)
        now = datetime.now(timezone.utc)
        if (now - created) < timedelta(hours=timeout_hours):
            logger.debug(
                "DelegationManager: Request %s not yet eligible for auto-delegation",
                request_id,
            )
            return None

        delegate_id = self.find_delegate(request.requested_by, request.required_role)
        if delegate_id is None:
            logger.info(
                "DelegationManager: No delegate found for request %s", request_id,
            )
            return None

        record = DelegationRecord(
            original_approver=request.requested_by,
            delegated_to=delegate_id,
            action_type=request.action_type,
            rule_id="auto",
        )

        with self._lock:
            self._persist_record(record, insert=True)

        logger.info(
            "DelegationManager: Auto-delegated request %s from user %d → user %d",
            request_id, request.requested_by, delegate_id,
        )
        return delegate_id

    # ── Query Methods ──────────────────────────────────────

    def get_active_delegations(self, user_id: int = 0) -> List[DelegationRule]:
        """Return active delegation rules, optionally filtered by user_id."""
        def _do_query() -> List[DelegationRule]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            if user_id:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT * FROM delegation_rules
                       WHERE from_user_id = ? AND active = 1
                       ORDER BY created_at DESC""",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT * FROM delegation_rules
                       WHERE active = 1
                       ORDER BY created_at DESC""",
                ).fetchall()
            conn.close()
            return [self._row_to_rule(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def get_delegation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent delegation records as dictionaries."""
        def _do_query() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM delegation_records
                   ORDER BY delegated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()
            return [
                {
                    "record_id": r["record_id"],
                    "rule_id": r["rule_id"],
                    "original_approver": r["original_approver"],
                    "delegated_to": r["delegated_to"],
                    "action_type": r["action_type"],
                    "delegated_at": r["delegated_at"],
                    "acknowledged": bool(r["acknowledged"]),
                }
                for r in rows
            ]

        return self._with_retry(_do_query, fallback=[])
