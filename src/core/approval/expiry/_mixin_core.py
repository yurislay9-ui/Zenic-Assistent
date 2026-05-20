"""
Expiry Manager — Core Mixin.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ._types import ExpiryConfig, ExpiryRecord
from ._mixin_persistence import ExpiryPersistenceMixin

logger = logging.getLogger(__name__)


class ExpiryManager(ExpiryPersistenceMixin):
    """Manages approval request expiration with auto-revert.

    When a request expires, the auto-revert action is executed via
    RollbackManager. Warning notifications are sent at configurable
    intervals before expiry.
    """

    def __init__(
        self,
        db_path: str = "expiry.sqlite",
        config: Optional[ExpiryConfig] = None,
    ) -> None:
        self._db_path = db_path
        self._config = config or ExpiryConfig()
        import threading
        self._lock = threading.RLock()
        self._init_db()

    # ── Core Operations ────────────────────────────────────

    def set_expiry(
        self,
        request_id: str,
        ttl_seconds: Optional[int] = None,
        config: Optional[ExpiryConfig] = None,
        revert_action: Optional[Dict[str, Any]] = None,
    ) -> ExpiryRecord:
        """Set an expiry for an approval request."""
        if not request_id:
            raise ValueError("request_id is required")

        effective_config = config or self._config
        ttl = ttl_seconds if ttl_seconds is not None else effective_config.default_ttl_seconds

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=ttl)).isoformat()

        if revert_action is not None:
            effective_config = ExpiryConfig(
                default_ttl_seconds=effective_config.default_ttl_seconds,
                notification_schedule=effective_config.notification_schedule,
                auto_revert_enabled=effective_config.auto_revert_enabled,
                revert_action=revert_action,
            )

        record = ExpiryRecord(
            request_id=request_id,
            expires_at=expires_at,
            status="active",
        )

        with self._lock:
            self._persist_expiry_record(record, insert=True)

        if effective_config.revert_action:
            try:
                from ..rollback import get_rollback_manager
                rm = get_rollback_manager()
                rm.register_compensation(
                    request_id=request_id,
                    action_type=effective_config.revert_action.get("type", "restore_state"),
                    payload=effective_config.revert_action.get("data", {}),
                    description=effective_config.revert_action.get("description", "Auto-revert on expiry"),
                )
            except Exception as exc:
                logger.debug("ExpiryManager: compensation registration failed: %s", exc)

        logger.info(
            "ExpiryManager: Set expiry for request %s — TTL=%ds, expires_at=%s",
            request_id, ttl, expires_at,
        )
        return record

    def check_expired(self) -> List[ExpiryRecord]:
        """Check for newly expired records and process them."""
        active_records = self._get_active_records()
        newly_expired: List[ExpiryRecord] = []

        for record in active_records:
            if record.is_expired():
                record.status = "expired"
                with self._lock:
                    self._persist_expiry_record(record, insert=False)

                newly_expired.append(record)

                if self._config.auto_revert_enabled:
                    self.execute_revert(record.request_id)

                self._send_expiry_notification(record)

                logger.info(
                    "ExpiryManager: Request %s expired — auto_revert=%s",
                    record.request_id, self._config.auto_revert_enabled,
                )

        return newly_expired

    def execute_revert(self, request_id: str) -> Dict[str, Any]:
        """Execute the revert action for an expired request."""
        record = self.get_expiry_record(request_id)
        if record is None:
            logger.warning("ExpiryManager: No expiry record for request %s", request_id)
            return {"success": False, "error": "Expiry record not found"}

        if record.status not in ("active", "expired"):
            logger.info(
                "ExpiryManager: Request %s is %s, cannot revert",
                request_id, record.status,
            )
            return {"success": False, "error": f"Request is {record.status}"}

        try:
            from ..rollback import get_rollback_manager, RollbackTrigger
            rm = get_rollback_manager()
            rollback_record = rm.execute_rollback(
                request_id=request_id,
                trigger=RollbackTrigger.APPROVAL_EXPIRED,
            )

            record.status = "reverted"
            record.reverted_at = datetime.now(timezone.utc).isoformat()
            record.revert_result = rollback_record.to_dict()

            with self._lock:
                self._persist_expiry_record(record, insert=False)

            self._record_audit_event(request_id, record)

            logger.info(
                "ExpiryManager: Reverted request %s — rollback_id=%s",
                request_id, rollback_record.rollback_id,
            )
            return {"success": True, "rollback": rollback_record.to_dict()}

        except Exception as exc:
            logger.error(
                "ExpiryManager: Revert failed for request %s — %s",
                request_id, exc,
            )
            return {"success": False, "error": str(exc)}

    def cancel_expiry(self, request_id: str) -> bool:
        """Cancel an active expiry (e.g., when request is approved)."""
        with self._lock:
            record = self.get_expiry_record(request_id)
            if record is None:
                logger.warning(
                    "ExpiryManager: No expiry record for request %s", request_id,
                )
                return False

            if record.status != "active":
                logger.info(
                    "ExpiryManager: Request %s is %s, cannot cancel",
                    request_id, record.status,
                )
                return False

            record.status = "cancelled"
            self._persist_expiry_record(record, insert=False)

        logger.info("ExpiryManager: Cancelled expiry for request %s", request_id)
        return True

    def get_expiry_record(self, request_id: str) -> Optional[ExpiryRecord]:
        """Get the expiry record for a request."""
        def _do_find() -> Optional[ExpiryRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM expiry_records WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_expiry_record(row)

        return self._with_retry(_do_find, fallback=None)

    def get_notification_schedule(self, request_id: str) -> List[int]:
        """Get the notification schedule (minutes before expiry thresholds)."""
        return list(self._config.notification_schedule)

    def check_notifications_due(self) -> List[Tuple[str, int]]:
        """Check which requests need expiry warning notifications."""
        active_records = self._get_active_records()
        notifications_due: List[Tuple[str, int]] = []

        for record in active_records:
            minutes = record.minutes_remaining()
            for threshold in self._config.notification_schedule:
                threshold_key = f"{threshold}min"
                if minutes <= threshold and threshold_key not in str(record.notification_sent_at):
                    notifications_due.append((record.request_id, threshold))
                    break

        return notifications_due

    # ── Integration Helpers ────────────────────────────────

    def _send_expiry_notification(self, record: ExpiryRecord) -> None:
        """Send an expiry notification via NotificationDispatcher."""
        try:
            from ..notification import (
                get_notification_dispatcher,
                NotificationEvent,
                NotificationPriority,
            )
            dispatcher = get_notification_dispatcher()
            dispatcher.dispatch(
                event=NotificationEvent.APPROVAL_EXPIRED,
                request_id=record.request_id,
                recipient_id="system",
                title="Approval Expired",
                body=f"Approval request {record.request_id} has expired and will be reverted.",
                priority=NotificationPriority.HIGH,
            )
        except Exception as exc:
            logger.debug("ExpiryManager: notification dispatch failed: %s", exc)

    def _record_audit_event(
        self, request_id: str, record: ExpiryRecord,
    ) -> None:
        """Record an EXPIRY_REVERTED event in the audit merkle trail."""
        try:
            from ..audit_merkle import get_approval_audit_merkle
            audit = get_approval_audit_merkle()
            audit.record_event(
                request_id=request_id,
                event_type="EXPIRY_REVERTED",
                actor_id="expiry_manager",
                actor_name="ExpiryManager",
                details={
                    "reverted_at": record.reverted_at,
                    "status": record.status,
                },
            )
        except Exception as exc:
            logger.debug("ExpiryManager: audit event recording failed: %s", exc)
