"""
Zenic-Agents Asistente - Escalation Manager (Phase 5)

SLA-based auto-escalation for approval requests. If no decision is made
within the SLA window, the request is automatically escalated to the
next level in the hierarchy.

Persistence: SQLite with retry logic (delegated to _db_helpers).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ._types import (
    EscalationLevel,
    SLAPolicy,
    EscalationSLA,
    _DEFAULT_SLA_POLICIES,
)
from ._db_helpers import (
    init_db as _init_db,
    load_sla_policies as _load_sla_policies,
    persist_sla_policy as _persist_sla_policy,
    persist_escalation_sla as _persist_escalation_sla,
    record_escalation_history as _record_escalation_history,
    find_escalation_sla as _find_escalation_sla,
    get_active_slas as _get_active_slas,
    get_escalation_history_rows as _get_escalation_history_rows,
)

logger = logging.getLogger(__name__)


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
        _init_db(self._db_path)
        _load_sla_policies(self._db_path, self._sla_policies)

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
            _persist_sla_policy(self._db_path, policy)

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
        """Create an SLA tracking record for an approval request."""
        if not request_id:
            raise ValueError("request_id is required")

        policy = self.get_sla_policy(initial_level)
        now = datetime.now(timezone.utc)

        if policy.max_response_time_ms > 0:
            deadline = now + timedelta(milliseconds=policy.max_response_time_ms)
            sla_deadline = deadline.isoformat()
        else:
            sla_deadline = (now + timedelta(days=365)).isoformat()

        sla = EscalationSLA(
            request_id=request_id,
            current_level=initial_level,
            target_role=policy.role,
            sla_deadline=sla_deadline,
        )

        with self._lock:
            _persist_escalation_sla(self._db_path, sla, insert=True)

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
        slas = _get_active_slas(self._db_path)
        breached: List[EscalationSLA] = []

        for sla in slas:
            if sla.is_breached() and not sla.breached:
                sla.breached = True
                with self._lock:
                    _persist_escalation_sla(self._db_path, sla, insert=False)
                breached.append(sla)

                logger.info(
                    "EscalationManager: SLA breached for request %s at level %s",
                    sla.request_id, sla.current_level.name,
                )

        return breached

    def auto_escalate_breached(self) -> List[EscalationSLA]:
        """Auto-escalate all breached requests that have auto_escalate=True."""
        breached = self.check_sla_breaches()
        escalated: List[EscalationSLA] = []

        for sla in breached:
            policy = self.get_sla_policy(sla.current_level)
            if not policy.auto_escalate:
                continue

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

            _record_escalation_history(
                self._db_path,
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
            sla.breached = False

            with self._lock:
                _persist_escalation_sla(self._db_path, sla, insert=False)

            self._send_escalation_notification(sla)
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
        """Manually escalate a request to a specific level."""
        sla = _find_escalation_sla(self._db_path, request_id)
        if sla is None:
            sla = self.create_escalation_sla(request_id)

        from_level = sla.current_level
        policy = self.get_sla_policy(to_level)
        now = datetime.now(timezone.utc)

        if policy.max_response_time_ms > 0:
            deadline = now + timedelta(milliseconds=policy.max_response_time_ms)
            sla_deadline = deadline.isoformat()
        else:
            sla_deadline = (now + timedelta(days=365)).isoformat()

        _record_escalation_history(
            self._db_path,
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
            _persist_escalation_sla(self._db_path, sla, insert=False)

        self._send_escalation_notification(sla)
        self._record_audit_event(request_id, sla)

        logger.info(
            "EscalationManager: Manually escalated request %s from %s to %s "
            "by %s — reason: %s",
            request_id, from_level.name, to_level.name, escalated_by, reason[:50],
        )
        return sla

    def get_escalation_history(self, request_id: str) -> List[Dict[str, Any]]:
        """Get the escalation history for a request."""
        return _get_escalation_history_rows(self._db_path, request_id)

    def get_current_level(self, request_id: str) -> Optional[EscalationSLA]:
        """Get the current SLA level for a request."""
        return _find_escalation_sla(self._db_path, request_id)

    # ── Private Helpers (non-DB) ───────────────────────────

    def _send_escalation_notification(self, sla: EscalationSLA) -> None:
        """Send an escalation notification via NotificationDispatcher."""
        try:
            from ..notification import (
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
            from ..audit_merkle import get_approval_audit_merkle
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
