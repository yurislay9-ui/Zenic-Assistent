"""Helper methods extracted from escalation."""

from __future__ import annotations

import json
import sqlite3
from ._types import EscalationLevel, SLAPolicy, EscalationSLA

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _init_db(self) -> None:
        """Create the escalation tables if they do not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS sla_policies (
                    level INTEGER PRIMARY KEY,
                    role TEXT NOT NULL,
                    max_response_time_ms INTEGER NOT NULL,
                    auto_escalate INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS escalation_slas (
                    request_id TEXT PRIMARY KEY,
                    current_level INTEGER NOT NULL DEFAULT 0,
                    target_role TEXT NOT NULL,
                    sla_deadline TEXT NOT NULL,
                    breached INTEGER NOT NULL DEFAULT 0,
                    auto_escalated INTEGER NOT NULL DEFAULT 0,
                    escalated_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS escalation_history (
                    history_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    from_level INTEGER NOT NULL,
                    to_level INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    escalated_by TEXT NOT NULL DEFAULT '',
                    escalated_at TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_escalation_sla_deadline
                ON escalation_slas(sla_deadline, breached)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_escalation_history_request
                ON escalation_history(request_id, escalated_at DESC)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)
        self._load_sla_policies()

    # ── SLA Policy Management ──────────────────────────────


    def _load_sla_policies(self) -> None:
        """Load SLA policies from the database, overriding defaults."""
        def _do_load() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM sla_policies").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
            conn.close()
            for row in rows:
                level = EscalationLevel(row["level"])
                self._sla_policies[level] = SLAPolicy(
                    level=level,
                    role=row["role"],
                    max_response_time_ms=row["max_response_time_ms"],
                    auto_escalate=bool(row["auto_escalate"]),
                )

        self._with_retry(_do_load)


    def _persist_sla_policy(self, policy: SLAPolicy) -> None:
        """Persist an SLA policy to the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO sla_policies
                   (level, role, max_response_time_ms, auto_escalate)
                   VALUES (?, ?, ?, ?)""",
                (
                    policy.level.value,
                    policy.role,
                    policy.max_response_time_ms,
                    int(policy.auto_escalate),
                ),
            )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)


    def _persist_escalation_sla(
        self, sla: EscalationSLA, *, insert: bool,
    ) -> None:
        """Insert or update an escalation SLA record."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO escalation_slas
                       (request_id, current_level, target_role, sla_deadline,
                        breached, auto_escalated, escalated_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sla.request_id,
                        sla.current_level.value,
                        sla.target_role,
                        sla.sla_deadline,
                        int(sla.breached),
                        int(sla.auto_escalated),
                        sla.escalated_at,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE escalation_slas SET
                       current_level=?, target_role=?, sla_deadline=?,
                       breached=?, auto_escalated=?, escalated_at=?
                       WHERE request_id=?""",
                    (
                        sla.current_level.value,
                        sla.target_role,
                        sla.sla_deadline,
                        int(sla.breached),
                        int(sla.auto_escalated),
                        sla.escalated_at,
                        sla.request_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)


    def _record_escalation_history(
        self,
        request_id: str,
        from_level: EscalationLevel,
        to_level: EscalationLevel,
        reason: str,
        escalated_by: str,
    ) -> None:
        """Record an escalation event in the history table."""
        history_id = f"esh-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        def _do_record() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO escalation_history
                   (history_id, request_id, from_level, to_level,
                    reason, escalated_by, escalated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    history_id,
                    request_id,
                    from_level.value,
                    to_level.value,
                    reason,
                    escalated_by,
                    now,
                ),
            )
            conn.commit()
            conn.close()

        self._with_retry(_do_record)


    def _send_escalation_notification(self, sla: EscalationSLA) -> None:
        """Send an escalation notification via NotificationDispatcher."""
        try:
            from .notification import (
                get_notification_dispatcher,
                NotificationEvent,
                NotificationPriority,
            )
            dispatcher = get_notification_dispatcher()
            dispatcher.dispatch(
                event=NotificationEvent.APPROVAL_ESCALATED,
                request_id=sla.request_id,
                recipient_id=sla.target_role,
                title="Approval Escalated",
                body=(
                    f"Approval request {sla.request_id} has been escalated "
                    f"to {sla.current_level.name} ({sla.target_role})."
                ),
                priority=NotificationPriority.HIGH,
                metadata={
                    "escalation_level": sla.current_level.value,
                    "target_role": sla.target_role,
                },
            )
        except Exception as exc:
            logger.debug("EscalationManager: notification dispatch failed: %s", exc)


    def _record_audit_event(
        self, request_id: str, sla: EscalationSLA,
    ) -> None:
        """Record an ESCALATION_TRIGGERED event in the audit merkle trail."""
        try:
            from .audit_merkle import get_approval_audit_merkle
            audit = get_approval_audit_merkle()
            audit.record_event(
                request_id=request_id,
                event_type="ESCALATION_TRIGGERED",
                actor_id="escalation_manager",
                actor_name="EscalationManager",
                details={
                    "current_level": sla.current_level.value,
                    "target_role": sla.target_role,
                    "auto_escalated": sla.auto_escalated,
                },
            )
        except Exception as exc:
            logger.debug("EscalationManager: audit event recording failed: %s", exc)


    def _row_to_escalation_sla(row: sqlite3.Row) -> EscalationSLA:
        """Convert a database row to an EscalationSLA."""
        return EscalationSLA(
            request_id=row["request_id"],
            current_level=EscalationLevel(row["current_level"]),
            target_role=row["target_role"],
            sla_deadline=row["sla_deadline"],
            breached=bool(row["breached"]),
            auto_escalated=bool(row["auto_escalated"]),
            escalated_at=row["escalated_at"],
        )


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
                    "EscalationManager: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("EscalationManager: DB error — %s", exc)
                break
        logger.error("EscalationManager: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_escalation_instance: Optional[EscalationManager] = None
_escalation_lock = threading.Lock()


def get_escalation_manager(
    db_path: str = "escalation.sqlite",
) -> EscalationManager:
    """Get or create the global EscalationManager instance."""
    global _escalation_instance
    with _escalation_lock:
        if _escalation_instance is None:
            _escalation_instance = EscalationManager(db_path=db_path)
        return _escalation_instance


def reset_escalation_manager() -> None:
    """Reset the global EscalationManager (for testing)."""
    global _escalation_instance
    _escalation_instance = None


__all__ = [
    "EscalationLevel",
    "SLAPolicy",
    "EscalationSLA",
    "EscalationManager",
    "get_escalation_manager",
    "reset_escalation_manager",
]

