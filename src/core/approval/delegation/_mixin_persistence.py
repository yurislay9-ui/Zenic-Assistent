"""
Delegation Manager — Persistence Mixin.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, List, Optional

from ._types import DelegationRule, DelegationRecord, _MAX_RETRIES, _RETRY_DELAY

logger = logging.getLogger(__name__)


class DelegationPersistenceMixin:
    """Persistence helpers for DelegationManager."""

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
