"""
Zenic-Agents Asistente - Escalation with SLAs (Phase 5)

SLA-based auto-escalation for approval requests. If no decision is made
within the SLA window, the request is automatically escalated to the
next level in the hierarchy.

Escalation levels:
  L0_DIRECT (0):    reviewer      — 60min SLA, auto_escalate=True
  L1_TEAM_LEAD (1): team_lead     — 120min SLA, auto_escalate=True
  L2_DIRECTOR (2):  director      — 240min SLA, auto_escalate=True
  L3_C_SUITE (3):   c_suite       — no limit, auto_escalate=False

Integration:
  - Called by the approval engine when creating requests.
  - Notifies via NotificationDispatcher on escalation.

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
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


class EscalationLevel(int, Enum):
    """Escalation hierarchy levels."""
    L0_DIRECT = 0
    L1_TEAM_LEAD = 1
    L2_DIRECTOR = 2
    L3_C_SUITE = 3


@dataclass
class SLAPolicy:
    """SLA policy for an escalation level."""

    level: EscalationLevel = EscalationLevel.L0_DIRECT
    role: str = "reviewer"
    max_response_time_ms: int = 3600000  # 60 minutes in ms
    auto_escalate: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "level": self.level.value,
            "role": self.role,
            "max_response_time_ms": self.max_response_time_ms,
            "auto_escalate": self.auto_escalate,
        }


@dataclass
class EscalationSLA:
    """Tracks the SLA state for a specific approval request."""

    request_id: str = ""
    current_level: EscalationLevel = EscalationLevel.L0_DIRECT
    target_role: str = "reviewer"
    sla_deadline: str = ""
    breached: bool = False
    auto_escalated: bool = False
    escalated_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id is required")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "request_id": self.request_id,
            "current_level": self.current_level.value,
            "target_role": self.target_role,
            "sla_deadline": self.sla_deadline,
            "breached": self.breached,
            "auto_escalated": self.auto_escalated,
            "escalated_at": self.escalated_at,
        }

    def is_breached(self) -> bool:
        """Check if the SLA has been breached based on current time."""
        if not self.sla_deadline:
            return False
        try:
            deadline = datetime.fromisoformat(self.sla_deadline)
            return datetime.now(timezone.utc) > deadline
        except (ValueError, TypeError):
            return False


# Default SLA policies
_DEFAULT_SLA_POLICIES: Dict[EscalationLevel, SLAPolicy] = {
    EscalationLevel.L0_DIRECT: SLAPolicy(
        level=EscalationLevel.L0_DIRECT,
        role="reviewer",
        max_response_time_ms=60 * 60 * 1000,  # 60 min
        auto_escalate=True,
    ),
    EscalationLevel.L1_TEAM_LEAD: SLAPolicy(
        level=EscalationLevel.L1_TEAM_LEAD,
        role="team_lead",
        max_response_time_ms=120 * 60 * 1000,  # 120 min
        auto_escalate=True,
    ),
    EscalationLevel.L2_DIRECTOR: SLAPolicy(
        level=EscalationLevel.L2_DIRECTOR,
        role="director",
        max_response_time_ms=240 * 60 * 1000,  # 240 min
        auto_escalate=True,
    ),
    EscalationLevel.L3_C_SUITE: SLAPolicy(
        level=EscalationLevel.L3_C_SUITE,
        role="c_suite",
        max_response_time_ms=0,  # No limit
        auto_escalate=False,
    ),
}


class EscalationManager:
    """Manages SLA-based escalation for approval requests.

    If no decision is made within the SLA window, the request is
    automatically escalated to the next level. Notifies via
    NotificationDispatcher on escalation.
    """

    def __init__(self, db_path: str = "escalation.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._sla_policies: Dict[EscalationLevel, SLAPolicy] = dict(_DEFAULT_SLA_POLICIES)
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the escalation tables if they do not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sla_policies (
                    level INTEGER PRIMARY KEY,
                    role TEXT NOT NULL,
                    max_response_time_ms INTEGER NOT NULL,
                    auto_escalate INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
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
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_escalation_sla_deadline
                ON escalation_slas(sla_deadline, breached)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_escalation_history_request
                ON escalation_history(request_id, escalated_at DESC)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)
        self._load_sla_policies()

    # ── SLA Policy Management ──────────────────────────────

    def set_sla_policy(
        self,
        level: EscalationLevel,
        role: str,
        max_response_time_ms: int,
        auto_escalate: bool,
    ) -> SLAPolicy:
        """Set or update an SLA policy for an escalation level."""
        policy = SLAPolicy(
            level=level,
            role=role,
            max_response_time_ms=max_response_time_ms,
            auto_escalate=auto_escalate,
        )
        with self._lock:
            self._sla_policies[level] = policy
            self._persist_sla_policy(policy)

        logger.info(
            "EscalationManager: Set SLA policy for %s — role=%s, "
            "max_response=%dms, auto_escalate=%s",
            level.name, role, max_response_time_ms, auto_escalate,
        )
        return policy

    def get_sla_policy(self, level: EscalationLevel) -> SLAPolicy:
        """Get the SLA policy for an escalation level."""
        return self._sla_policies.get(level, _DEFAULT_SLA_POLICIES[level])

    # ── Core Operations ────────────────────────────────────

    def create_escalation_sla(
        self,
        request_id: str,
        initial_level: EscalationLevel = EscalationLevel.L0_DIRECT,
    ) -> EscalationSLA:
        """Create an SLA tracking record for an approval request.

        Computes the SLA deadline based on the policy for the initial level.
        """
        if not request_id:
            raise ValueError("request_id is required")

        policy = self.get_sla_policy(initial_level)
        now = datetime.now(timezone.utc)

        if policy.max_response_time_ms > 0:
            deadline = now + timedelta(milliseconds=policy.max_response_time_ms)
            sla_deadline = deadline.isoformat()
        else:
            # No limit — set far-future deadline
            sla_deadline = (now + timedelta(days=365)).isoformat()

        sla = EscalationSLA(
            request_id=request_id,
            current_level=initial_level,
            target_role=policy.role,
            sla_deadline=sla_deadline,
        )

        with self._lock:
            self._persist_escalation_sla(sla, insert=True)

        logger.info(
            "EscalationManager: Created SLA for request %s — level=%s, "
            "role=%s, deadline=%s",
            request_id, initial_level.name, policy.role, sla_deadline,
        )
        return sla

    def check_sla_breaches(self) -> List[EscalationSLA]:
        """Check for SLA breaches.

        Returns the list of currently breached SLAs (not yet auto-escalated).
        """
        slas = self._get_active_slas()
        breached: List[EscalationSLA] = []

        for sla in slas:
            if sla.is_breached() and not sla.breached:
                sla.breached = True
                with self._lock:
                    self._persist_escalation_sla(sla, insert=False)
                breached.append(sla)

                logger.info(
                    "EscalationManager: SLA breached for request %s at level %s",
                    sla.request_id, sla.current_level.name,
                )

        return breached

    def auto_escalate_breached(self) -> List[EscalationSLA]:
        """Auto-escalate all breached requests that have auto_escalate=True.

        Returns the list of newly escalated SLAs.
        """
        breached = self.check_sla_breaches()
        escalated: List[EscalationSLA] = []

        for sla in breached:
            policy = self.get_sla_policy(sla.current_level)
            if not policy.auto_escalate:
                continue

            # Escalate to the next level
            next_level = EscalationLevel(sla.current_level.value + 1)
            if next_level.value > EscalationLevel.L3_C_SUITE.value:
                logger.warning(
                    "EscalationManager: Request %s already at max level, "
                    "cannot auto-escalate further",
                    sla.request_id,
                )
                continue

            next_policy = self.get_sla_policy(next_level)
            now = datetime.now(timezone.utc)

            if next_policy.max_response_time_ms > 0:
                deadline = now + timedelta(milliseconds=next_policy.max_response_time_ms)
                sla_deadline = deadline.isoformat()
            else:
                sla_deadline = (now + timedelta(days=365)).isoformat()

            # Record escalation history
            self._record_escalation_history(
                request_id=sla.request_id,
                from_level=sla.current_level,
                to_level=next_level,
                reason="SLA breach auto-escalation",
                escalated_by="system",
            )

            sla.current_level = next_level
            sla.target_role = next_policy.role
            sla.sla_deadline = sla_deadline
            sla.auto_escalated = True
            sla.escalated_at = now.isoformat()
            sla.breached = False  # Reset for new SLA window

            with self._lock:
                self._persist_escalation_sla(sla, insert=False)

            # Send escalation notification
            self._send_escalation_notification(sla)

            # Record audit event
            self._record_audit_event(sla.request_id, sla)

            escalated.append(sla)

            logger.info(
                "EscalationManager: Auto-escalated request %s from %s to %s",
                sla.request_id,
                EscalationLevel(sla.current_level.value - 1).name,
                next_level.name,
            )

        return escalated

    def manual_escalate(
        self,
        request_id: str,
        to_level: EscalationLevel,
        reason: str,
        escalated_by: str,
    ) -> EscalationSLA:
        """Manually escalate a request to a specific level.

        Args:
            request_id: The approval request ID.
            to_level: The level to escalate to.
            reason: Reason for the escalation.
            escalated_by: Who triggered the escalation.

        Returns:
            The updated EscalationSLA.
        """
        sla = self._find_escalation_sla(request_id)
        if sla is None:
            # Create one if it doesn't exist
            sla = self.create_escalation_sla(request_id)

        from_level = sla.current_level
        policy = self.get_sla_policy(to_level)
        now = datetime.now(timezone.utc)

        if policy.max_response_time_ms > 0:
            deadline = now + timedelta(milliseconds=policy.max_response_time_ms)
            sla_deadline = deadline.isoformat()
        else:
            sla_deadline = (now + timedelta(days=365)).isoformat()

        # Record escalation history
        self._record_escalation_history(
            request_id=request_id,
            from_level=from_level,
            to_level=to_level,
            reason=reason,
            escalated_by=escalated_by,
        )

        sla.current_level = to_level
        sla.target_role = policy.role
        sla.sla_deadline = sla_deadline
        sla.escalated_at = now.isoformat()
        sla.breached = False

        with self._lock:
            self._persist_escalation_sla(sla, insert=False)

        # Send escalation notification
        self._send_escalation_notification(sla)

        # Record audit event
        self._record_audit_event(request_id, sla)

        logger.info(
            "EscalationManager: Manually escalated request %s from %s to %s "
            "by %s — reason: %s",
            request_id, from_level.name, to_level.name, escalated_by, reason[:50],
        )
        return sla

    def get_escalation_history(self, request_id: str) -> List[Dict[str, Any]]:
        """Get the escalation history for a request."""
        def _do_query() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM escalation_history
                   WHERE request_id = ?
                   ORDER BY escalated_at ASC""",
                (request_id,),
            ).fetchall()
            conn.close()
            return [
                {
                    "history_id": r["history_id"],
                    "request_id": r["request_id"],
                    "from_level": r["from_level"],
                    "to_level": r["to_level"],
                    "reason": r["reason"],
                    "escalated_by": r["escalated_by"],
                    "escalated_at": r["escalated_at"],
                }
                for r in rows
            ]

        return self._with_retry(_do_query, fallback=[])

    def get_current_level(self, request_id: str) -> Optional[EscalationSLA]:
        """Get the current SLA level for a request."""
        return self._find_escalation_sla(request_id)

    # ── Private Helpers ────────────────────────────────────

    def _find_escalation_sla(self, request_id: str) -> Optional[EscalationSLA]:
        """Find an escalation SLA by request ID."""
        def _do_find() -> Optional[EscalationSLA]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM escalation_slas WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_escalation_sla(row)

        return self._with_retry(_do_find, fallback=None)

    def _get_active_slas(self) -> List[EscalationSLA]:
        """Get all active (non-breached) SLA records."""
        def _do_query() -> List[EscalationSLA]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM escalation_slas
                   WHERE breached = 0
                   ORDER BY sla_deadline ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_escalation_sla(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def _load_sla_policies(self) -> None:
        """Load SLA policies from the database, overriding defaults."""
        def _do_load() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM sla_policies").fetchall()
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
            conn.execute(
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
                conn.execute(
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
                conn.execute(
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
            conn.execute(
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

    @staticmethod
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
