"""escalation — Core implementation."""

from __future__ import annotations

from ._types import *  # noqa: F403
from ._helpers import _init_db, _load_sla_policies, _persist_sla_policy, _persist_escalation_sla, _record_escalation_history, _send_escalation_notification, _record_audit_event, _row_to_escalation_sla, _with_retry

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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT * FROM escalation_slas
                   WHERE breached = 0
                   ORDER BY sla_deadline ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_escalation_sla(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    @staticmethod
    @staticmethod