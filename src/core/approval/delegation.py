"""
Zenic-Agents Asistente - Delegation Manager (Phase C3)

Handles approver substitution when the primary approver is unavailable.
Supports:
  - Explicit delegation rules (from_user → to_user, scoped by role)
  - Automatic delegation for pending approvals that exceed a timeout
  - Role hierarchy verification via auth_parts.ROLE_HIERARCHY
  - Acknowledgement tracking for audit purposes

Persistence: SQLite with retry logic.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class DelegationRule:
    """A rule that delegates approval authority from one user to another."""

    rule_id: str = ""
    from_user_id: int = 0
    to_user_id: int = 0
    from_role: str = ""
    to_role: str = ""
    active: bool = True
    expires_at: str = ""
    created_at: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = f"del-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def is_active(self) -> bool:
        """Check whether this rule is currently active and not expired."""
        if not self.active:
            return False
        if not self.expires_at:
            return True  # No expiry = always active (while active=True)
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) < exp
        except (ValueError, TypeError):
            return self.active

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "rule_id": self.rule_id,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "from_role": self.from_role,
            "to_role": self.to_role,
            "active": self.active,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass
class DelegationRecord:
    """An actual delegation event (when a rule is applied to a request)."""

    record_id: str = ""
    rule_id: str = ""
    original_approver: int = 0
    delegated_to: int = 0
    action_type: str = ""
    delegated_at: str = ""
    acknowledged: bool = False

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"dlr-{uuid.uuid4().hex[:12]}"
        if not self.delegated_at:
            self.delegated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "rule_id": self.rule_id,
            "original_approver": self.original_approver,
            "delegated_to": self.delegated_to,
            "action_type": self.action_type,
            "delegated_at": self.delegated_at,
            "acknowledged": self.acknowledged,
        }


class DelegationManager:
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
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the delegation tables if they do not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS delegation_rules (
                    rule_id TEXT PRIMARY KEY,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    from_role TEXT NOT NULL,
                    to_role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS delegation_records (
                    record_id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    original_approver INTEGER NOT NULL,
                    delegated_to INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    delegated_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_del_rules_from
                ON delegation_rules(from_user_id, from_role, active)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_del_records_rule
                ON delegation_records(rule_id)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

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
        """Create a new delegation rule.

        Args:
            from_user_id: The user delegating their authority.
            to_user_id: The user receiving the authority.
            from_role: The role being delegated.
            to_role: The role of the delegatee.
            expires_hours: Hours until the rule expires (0 = use default).
            reason: Optional reason for the delegation.

        Returns:
            The created DelegationRule.
        """
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
        """Revoke (deactivate) a delegation rule.

        Returns True if the rule was found and revoked.
        """
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
        """Find an active delegate for the given user+role combination.

        Verifies that the delegate's role is sufficient in the hierarchy.
        Uses lazy import of ROLE_HIERARCHY from auth_parts.

        Returns the delegate user_id, or None if no suitable delegate exists.
        """
        # auth_parts removed — use fallback ROLE_HIERARCHY from auth_service stub
        from src.core.auth_service import ROLE_HIERARCHY

        with self._lock:
            rules = self._list_active_rules_for(user_id, role)

        for rule in rules:
            # Verify the delegate's role is at least as high as the delegator's
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
        """Acknowledge a delegation record.

        Returns True if the record was found and acknowledged.
        """
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
        """If an approval request is pending beyond *timeout_hours*, auto-delegate.

        Finds the original approver for the request, locates a delegate,
        and creates a delegation record.

        Returns the delegate user_id, or None if delegation was not possible.
        """
        # Lazy import to avoid circular dependency
        from .chain import get_approval_chain

        chain = get_approval_chain()
        request = chain.get_request(request_id)
        if request is None:
            logger.warning("DelegationManager: Request %s not found", request_id)
            return None

        # Check if the request is still pending
        if request.status.value != "pending":
            logger.info(
                "DelegationManager: Request %s is not pending (status=%s)",
                request_id, request.status.value,
            )
            return None

        # Check if the request has been pending long enough
        created = datetime.fromisoformat(request.created_at)
        now = datetime.now(timezone.utc)
        if (now - created) < timedelta(hours=timeout_hours):
            logger.debug(
                "DelegationManager: Request %s not yet eligible for auto-delegation",
                request_id,
            )
            return None

        # Find a delegate for the required role's approvers
        delegate_id = self.find_delegate(request.requested_by, request.required_role)
        if delegate_id is None:
            logger.info(
                "DelegationManager: No delegate found for request %s", request_id,
            )
            return None

        # Create a delegation record
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

    # ── Private Helpers ────────────────────────────────────

    def _list_active_rules_for(
        self, from_user_id: int, from_role: str,
    ) -> List[DelegationRule]:
        """List active delegation rules for a user+role."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM delegation_rules
                   WHERE from_user_id = ? AND from_role = ? AND active = 1
                   ORDER BY created_at DESC""",
                (from_user_id, from_role),
            ).fetchall()
        finally:
            conn.close()
        # Filter by is_active() which also checks expiry
        rules = [self._row_to_rule(r) for r in rows]
        return [r for r in rules if r.is_active()]

    def _find_rule(self, rule_id: str) -> Optional[DelegationRule]:
        """Find a delegation rule by ID."""
        def _do_find() -> Optional[DelegationRule]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM delegation_rules WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_rule(row)

        return self._with_retry(_do_find, fallback=None)

    def _find_record(self, record_id: str) -> Optional[DelegationRecord]:
        """Find a delegation record by ID."""
        def _do_find() -> Optional[DelegationRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM delegation_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return DelegationRecord(
                record_id=row["record_id"],
                rule_id=row["rule_id"],
                original_approver=row["original_approver"],
                delegated_to=row["delegated_to"],
                action_type=row["action_type"],
                delegated_at=row["delegated_at"],
                acknowledged=bool(row["acknowledged"]),
            )

        return self._with_retry(_do_find, fallback=None)

    def _persist_rule(self, rule: DelegationRule, *, insert: bool) -> None:
        """Insert or update a delegation rule."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO delegation_rules
                       (rule_id, from_user_id, to_user_id, from_role, to_role,
                        active, expires_at, created_at, reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rule.rule_id, rule.from_user_id, rule.to_user_id,
                        rule.from_role, rule.to_role, int(rule.active),
                        rule.expires_at, rule.created_at, rule.reason,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE delegation_rules SET
                       active=?, expires_at=?, reason=?
                       WHERE rule_id=?""",
                    (int(rule.active), rule.expires_at, rule.reason, rule.rule_id),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    def _persist_record(self, record: DelegationRecord, *, insert: bool) -> None:
        """Insert or update a delegation record."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO delegation_records
                       (record_id, rule_id, original_approver, delegated_to,
                        action_type, delegated_at, acknowledged)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.record_id, record.rule_id,
                        record.original_approver, record.delegated_to,
                        record.action_type, record.delegated_at,
                        int(record.acknowledged),
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE delegation_records SET acknowledged=?
                       WHERE record_id=?""",
                    (int(record.acknowledged), record.record_id),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> DelegationRule:
        """Convert a database row to a DelegationRule."""
        return DelegationRule(
            rule_id=row["rule_id"],
            from_user_id=row["from_user_id"],
            to_user_id=row["to_user_id"],
            from_role=row["from_role"],
            to_role=row["to_role"],
            active=bool(row["active"]),
            expires_at=row["expires_at"] or "",
            created_at=row["created_at"],
            reason=row["reason"] or "",
        )

    @staticmethod
    def _with_retry(
        fn: Any,
        fallback: Any = None,
        max_retries: int = _MAX_RETRIES,
    ) -> Any:
        """Execute *fn* with retry logic on database errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                logger.warning(
                    "DelegationManager: DB retry %d/%d — %s", attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("DelegationManager: DB error — %s", exc)
                break
        logger.error("DelegationManager: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_delegation_instance: Optional[DelegationManager] = None
_delegation_lock = threading.Lock()


def get_delegation_manager(
    db_path: str = "delegation.sqlite",
    default_timeout_hours: int = 24,
) -> DelegationManager:
    """Get or create the global DelegationManager instance."""
    global _delegation_instance
    with _delegation_lock:
        if _delegation_instance is None:
            _delegation_instance = DelegationManager(
                db_path=db_path,
                default_timeout_hours=default_timeout_hours,
            )
        return _delegation_instance


def reset_delegation_manager() -> None:
    """Reset the global DelegationManager (for testing)."""
    global _delegation_instance
    _delegation_instance = None


__all__ = [
    "DelegationRule",
    "DelegationRecord",
    "DelegationManager",
    "get_delegation_manager",
    "reset_delegation_manager",
]
