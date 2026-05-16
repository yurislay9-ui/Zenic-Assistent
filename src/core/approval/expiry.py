"""
Zenic-Agents Asistente - Expiration with Auto-Revert (Phase 5)

Manages expiration of approval requests with configurable TTL and
automatic revert when approvals expire. When a request expires, the
auto-revert action is executed via the RollbackManager.

Notification schedule:
  - Warning notifications are sent at configurable intervals before
    expiry (default: 60, 30, 10, 5 minutes before).

Integration:
  - ExpiryManager calls RollbackManager.execute_revert() on expiry.
  - ExpiryManager calls NotificationDispatcher for expiry warnings.
  - ExpiryManager records EXPIRY_REVERTED events in the audit trail.

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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class ExpiryConfig:
    """Configuration for approval expiration behavior."""

    default_ttl_seconds: int = 3600  # 1 hour
    notification_schedule: List[int] = field(
        default_factory=lambda: [60, 30, 10, 5]
    )  # minutes before expiry
    auto_revert_enabled: bool = True
    revert_action: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "default_ttl_seconds": self.default_ttl_seconds,
            "notification_schedule": self.notification_schedule,
            "auto_revert_enabled": self.auto_revert_enabled,
            "revert_action": self.revert_action,
        }


@dataclass
class ExpiryRecord:
    """Tracks the expiration state of an approval request."""

    request_id: str = ""
    expires_at: str = ""
    reverted_at: Optional[str] = None
    revert_result: Optional[Dict[str, Any]] = None
    notification_sent_at: List[str] = field(default_factory=list)
    status: str = "active"  # active/expired/reverted/cancelled

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id is required")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "request_id": self.request_id,
            "expires_at": self.expires_at,
            "reverted_at": self.reverted_at,
            "revert_result": self.revert_result,
            "notification_sent_at": self.notification_sent_at,
            "status": self.status,
        }

    def is_expired(self) -> bool:
        """Check if the record has expired based on the current time."""
        if self.status != "active":
            return False
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp
        except (ValueError, TypeError):
            return False

    def minutes_remaining(self) -> float:
        """Return minutes remaining until expiry."""
        if not self.expires_at:
            return float("inf")
        try:
            exp = datetime.fromisoformat(self.expires_at)
            delta = exp - datetime.now(timezone.utc)
            return max(0.0, delta.total_seconds() / 60.0)
        except (ValueError, TypeError):
            return 0.0


class ExpiryManager:
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
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the expiry records table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expiry_records (
                    request_id TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL,
                    reverted_at TEXT,
                    revert_result TEXT,
                    notification_sent_at TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expiry_status
                ON expiry_records(status, expires_at)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def set_expiry(
        self,
        request_id: str,
        ttl_seconds: Optional[int] = None,
        config: Optional[ExpiryConfig] = None,
        revert_action: Optional[Dict[str, Any]] = None,
    ) -> ExpiryRecord:
        """Set an expiry for an approval request.

        Args:
            request_id: The approval request ID.
            ttl_seconds: Time-to-live in seconds. Uses config default if not set.
            config: Optional override config.
            revert_action: Action to execute on expiry/revert.

        Returns:
            The created ExpiryRecord.
        """
        if not request_id:
            raise ValueError("request_id is required")

        effective_config = config or self._config
        ttl = ttl_seconds if ttl_seconds is not None else effective_config.default_ttl_seconds

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=ttl)).isoformat()

        # Store revert_action in metadata if provided
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

        # Register compensation with RollbackManager if revert_action provided
        if effective_config.revert_action:
            try:
                from .rollback import get_rollback_manager
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
        """Check for newly expired records and process them.

        Returns the list of newly expired records. If auto_revert_enabled,
        also triggers the revert action via RollbackManager.
        """
        active_records = self._get_active_records()
        newly_expired: List[ExpiryRecord] = []

        for record in active_records:
            if record.is_expired():
                record.status = "expired"
                with self._lock:
                    self._persist_expiry_record(record, insert=False)

                newly_expired.append(record)

                # Execute auto-revert if enabled
                if self._config.auto_revert_enabled:
                    self.execute_revert(record.request_id)

                # Send expiry notification
                self._send_expiry_notification(record)

                logger.info(
                    "ExpiryManager: Request %s expired — auto_revert=%s",
                    record.request_id, self._config.auto_revert_enabled,
                )

        return newly_expired

    def execute_revert(self, request_id: str) -> Dict[str, Any]:
        """Execute the revert action for an expired request.

        Called by check_expired() automatically or manually.
        Delegates to RollbackManager.execute_rollback().

        Returns:
            The revert result dict.
        """
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

        # Delegate to RollbackManager
        try:
            from .rollback import get_rollback_manager, RollbackTrigger
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

            # Record audit event
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
        """Cancel an active expiry (e.g., when request is approved).

        Returns True if the expiry was found and cancelled.
        """
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
            row = conn.execute(
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
        """Check which requests need expiry warning notifications.

        Returns list of (request_id, minutes_remaining) for requests
        that need an expiry warning notification.
        """
        active_records = self._get_active_records()
        notifications_due: List[Tuple[str, int]] = []

        for record in active_records:
            minutes = record.minutes_remaining()
            for threshold in self._config.notification_schedule:
                # Check if we're within the threshold and haven't sent this notification yet
                threshold_key = f"{threshold}min"
                if minutes <= threshold and threshold_key not in str(record.notification_sent_at):
                    notifications_due.append((record.request_id, threshold))
                    break  # Only one notification per check cycle

        return notifications_due

    # ── Private Helpers ────────────────────────────────────

    def _get_active_records(self) -> List[ExpiryRecord]:
        """Get all active expiry records."""
        def _do_query() -> List[ExpiryRecord]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM expiry_records
                   WHERE status = 'active'
                   ORDER BY expires_at ASC""",
            ).fetchall()
            conn.close()
            return [self._row_to_expiry_record(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def _send_expiry_notification(self, record: ExpiryRecord) -> None:
        """Send an expiry notification via NotificationDispatcher."""
        try:
            from .notification import (
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
            from .audit_merkle import get_approval_audit_merkle
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

    def _persist_expiry_record(
        self, record: ExpiryRecord, *, insert: bool,
    ) -> None:
        """Insert or update an expiry record."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            result_json = json.dumps(record.revert_result) if record.revert_result else None

            if insert:
                conn.execute(
                    """INSERT INTO expiry_records
                       (request_id, expires_at, reverted_at, revert_result,
                        notification_sent_at, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record.request_id,
                        record.expires_at,
                        record.reverted_at,
                        result_json,
                        json.dumps(record.notification_sent_at),
                        record.status,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE expiry_records SET
                       expires_at=?, reverted_at=?, revert_result=?,
                       notification_sent_at=?, status=?
                       WHERE request_id=?""",
                    (
                        record.expires_at,
                        record.reverted_at,
                        result_json,
                        json.dumps(record.notification_sent_at),
                        record.status,
                        record.request_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_expiry_record(row: sqlite3.Row) -> ExpiryRecord:
        """Convert a database row to an ExpiryRecord."""
        result_data = json.loads(row["revert_result"]) if row["revert_result"] else None
        return ExpiryRecord(
            request_id=row["request_id"],
            expires_at=row["expires_at"],
            reverted_at=row["reverted_at"],
            revert_result=result_data,
            notification_sent_at=json.loads(row["notification_sent_at"] or "[]"),
            status=row["status"],
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
                    "ExpiryManager: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("ExpiryManager: DB error — %s", exc)
                break
        logger.error("ExpiryManager: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_expiry_instance: Optional[ExpiryManager] = None
_expiry_lock = threading.Lock()


def get_expiry_manager(
    db_path: str = "expiry.sqlite",
    config: Optional[ExpiryConfig] = None,
) -> ExpiryManager:
    """Get or create the global ExpiryManager instance."""
    global _expiry_instance
    with _expiry_lock:
        if _expiry_instance is None:
            _expiry_instance = ExpiryManager(db_path=db_path, config=config)
        return _expiry_instance


def reset_expiry_manager() -> None:
    """Reset the global ExpiryManager (for testing)."""
    global _expiry_instance
    _expiry_instance = None


__all__ = [
    "ExpiryConfig",
    "ExpiryRecord",
    "ExpiryManager",
    "get_expiry_manager",
    "reset_expiry_manager",
]
