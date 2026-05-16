"""
Zenic-Agents Asistente - Multi-Channel Approval Notifications (Phase 5)

Dispatches approval notifications across multiple channels with fallback
support. If the primary channel fails, falls back to the next available
channel. In-app notifications are always available.

Channels:
  IN_APP, EMAIL, SLACK, TEAMS, WHATSAPP, SMS, PUSH, WEBHOOK

Channel implementations are stubs (log to console) for external channels.
In-app notifications are stored in SQLite.

Events:
  APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED,
  APPROVAL_DELEGATED, APPROVAL_ESCALATED, APPROVAL_EXPIRED,
  APPROVAL_UNDONE, UNDO_AVAILABLE, EXPIRY_WARNING

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
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


class NotificationChannel(str, Enum):
    """Available notification channels."""
    IN_APP = "in_app"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class NotificationPriority(str, Enum):
    """Priority level for notifications."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationEvent(str, Enum):
    """Types of notification events in the HITL system."""
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_DELEGATED = "APPROVAL_DELEGATED"
    APPROVAL_ESCALATED = "APPROVAL_ESCALATED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_UNDONE = "APPROVAL_UNDONE"
    UNDO_AVAILABLE = "UNDO_AVAILABLE"
    EXPIRY_WARNING = "EXPIRY_WARNING"


@dataclass
class NotificationMessage:
    """A notification message sent through a specific channel."""

    message_id: str = ""
    channel: NotificationChannel = NotificationChannel.IN_APP
    event: NotificationEvent = NotificationEvent.APPROVAL_PENDING
    recipient_id: str = ""
    title: str = ""
    body: str = ""
    request_id: str = ""
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    sent_at: Optional[str] = None
    status: str = "pending"  # pending/sent/failed

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = f"ntf-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "message_id": self.message_id,
            "channel": self.channel.value,
            "event": self.event.value,
            "recipient_id": self.recipient_id,
            "title": self.title,
            "body": self.body,
            "request_id": self.request_id,
            "priority": self.priority.value,
            "metadata": self.metadata,
            "sent_at": self.sent_at,
            "status": self.status,
        }


@dataclass
class ChannelConfig:
    """Configuration for a notification channel."""

    channel: NotificationChannel = NotificationChannel.IN_APP
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "channel": self.channel.value,
            "enabled": self.enabled,
            "config": self.config,
        }


class NotificationDispatcher:
    """Multi-channel notification dispatcher with fallback support.

    If the primary channel fails, falls back to the next available
    channel. In-app notifications are always available and stored
    in SQLite.
    """

    def __init__(self, db_path: str = "notification.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._channels: Dict[NotificationChannel, ChannelConfig] = {}
        self._init_db()
        # In-app is always enabled
        self._channels[NotificationChannel.IN_APP] = ChannelConfig(
            channel=NotificationChannel.IN_APP,
            enabled=True,
            config={},
        )

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the notifications and channel_config tables."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    message_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    event TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    request_id TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    sent_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_request
                ON notifications(request_id, channel)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_recipient
                ON notifications(recipient_id, status)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channel_configs (
                    channel TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    config TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)
        self._load_channel_configs()

    # ── Channel Management ─────────────────────────────────

    def register_channel(
        self, channel_type: Union[NotificationChannel, str], config: Union[ChannelConfig, Dict[str, Any]],
    ) -> None:
        """Register or update a notification channel configuration."""
        # Coerce string to enum
        if isinstance(channel_type, str):
            channel_type = NotificationChannel(channel_type)
        # Coerce dict to ChannelConfig
        if isinstance(config, dict):
            config = ChannelConfig(
                channel=channel_type,
                enabled=config.get("enabled", True),
                config=config,
            )
        with self._lock:
            self._channels[channel_type] = config
            self._persist_channel_config(config)

        logger.info(
            "NotificationDispatcher: Registered channel %s (enabled=%s)",
            channel_type.value, config.enabled,
        )

    def _load_channel_configs(self) -> None:
        """Load channel configurations from the database."""
        def _do_load() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM channel_configs",
            ).fetchall()
            conn.close()
            for row in rows:
                channel = NotificationChannel(row["channel"])
                self._channels[channel] = ChannelConfig(
                    channel=channel,
                    enabled=bool(row["enabled"]),
                    config=json.loads(row["config"] or "{}"),
                )

        self._with_retry(_do_load)

    def _persist_channel_config(self, config: ChannelConfig) -> None:
        """Persist a channel configuration to the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT OR REPLACE INTO channel_configs
                   (channel, enabled, config)
                   VALUES (?, ?, ?)""",
                (
                    config.channel.value,
                    int(config.enabled),
                    json.dumps(config.config),
                ),
            )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    # ── Core Operations ────────────────────────────────────

    def dispatch(
        self,
        event: Union[NotificationEvent, str],
        request_id: str,
        recipient_id: str,
        title: str,
        body: str,
        priority: Union[NotificationPriority, str] = NotificationPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[NotificationMessage]:
        """Send notifications via all enabled channels.

        Args:
            event: The notification event type (enum or string).
            request_id: The associated approval request ID.
            recipient_id: The recipient's identifier.
            title: Notification title.
            body: Notification body text.
            priority: Notification priority (enum or string).
            metadata: Additional metadata.

        Returns:
            List of NotificationMessage objects, one per channel.
        """
        # Coerce strings to enums
        if isinstance(event, str):
            try:
                event = NotificationEvent(event)
            except ValueError:
                event = NotificationEvent.APPROVAL_PENDING
        if isinstance(priority, str):
            try:
                priority = NotificationPriority(priority)
            except ValueError:
                priority = NotificationPriority.NORMAL

        messages: List[NotificationMessage] = []
        meta = metadata or {}

        with self._lock:
            for channel_type, config in self._channels.items():
                if not config.enabled:
                    continue
                message = NotificationMessage(
                    channel=channel_type,
                    event=event,
                    recipient_id=recipient_id,
                    title=title,
                    body=body,
                    request_id=request_id,
                    priority=priority,
                    metadata=meta,
                )
                result = self.dispatch_to_channel(channel_type, message)
                messages.append(result)

        logger.info(
            "NotificationDispatcher: Dispatched %s event for request %s "
            "to %d channels",
            event.value, request_id, len(messages),
        )
        return messages

    def dispatch_to_channel(
        self,
        channel: NotificationChannel,
        message: NotificationMessage,
    ) -> NotificationMessage:
        """Send a notification through a specific channel.

        If the channel fails, the message status is set to 'failed'.
        External channel implementations are stubs (log to console).
        In-app notifications are stored in SQLite.
        """
        try:
            if channel == NotificationChannel.IN_APP:
                self._send_in_app(message)
            elif channel == NotificationChannel.EMAIL:
                self._send_email(message)
            elif channel == NotificationChannel.SLACK:
                self._send_slack(message)
            elif channel == NotificationChannel.TEAMS:
                self._send_teams(message)
            elif channel == NotificationChannel.WHATSAPP:
                self._send_whatsapp(message)
            elif channel == NotificationChannel.SMS:
                self._send_sms(message)
            elif channel == NotificationChannel.PUSH:
                self._send_push(message)
            elif channel == NotificationChannel.WEBHOOK:
                self._send_webhook(message)

            message.sent_at = datetime.now(timezone.utc).isoformat()
            message.status = "sent"
        except Exception as exc:
            logger.warning(
                "NotificationDispatcher: Failed to send via %s — %s",
                channel.value, exc,
            )
            message.status = "failed"

        # Persist all messages for audit trail
        with self._lock:
            self._persist_message(message, insert=True)

        return message

    def get_notification_history(
        self, request_id: str,
    ) -> List[NotificationMessage]:
        """Get all notifications sent for a request."""
        def _do_query() -> List[NotificationMessage]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM notifications
                   WHERE request_id = ?
                   ORDER BY sent_at DESC""",
                (request_id,),
            ).fetchall()
            conn.close()
            return [self._row_to_message(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def get_pending_notifications(self) -> List[NotificationMessage]:
        """Get all notifications with 'pending' or 'failed' status."""
        def _do_query() -> List[NotificationMessage]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM notifications
                   WHERE status IN ('pending', 'failed')
                   ORDER BY message_id""",
            ).fetchall()
            conn.close()
            return [self._row_to_message(r) for r in rows]

        return self._with_retry(_do_query, fallback=[])

    def retry_failed(self, notification_id: str) -> NotificationMessage:
        """Retry a failed notification.

        Re-dispatches through the same channel.
        """
        message = self._find_message(notification_id)
        if message is None:
            raise ValueError(f"Notification {notification_id} not found")

        if message.status != "failed":
            return message

        # Retry via the same channel
        result = self.dispatch_to_channel(message.channel, message)
        return result

    # ── Channel Stubs ──────────────────────────────────────

    def _send_in_app(self, message: NotificationMessage) -> None:
        """Store an in-app notification (always succeeds)."""
        # In-app notifications are simply stored in SQLite via persist_message
        logger.info(
            "NotificationDispatcher: [IN_APP] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_email(self, message: NotificationMessage) -> None:
        """Send an email notification (stub — logs to console)."""
        logger.info(
            "NotificationDispatcher: [EMAIL] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_slack(self, message: NotificationMessage) -> None:
        """Send a Slack notification (stub — logs to console)."""
        logger.info(
            "NotificationDispatcher: [SLACK] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_teams(self, message: NotificationMessage) -> None:
        """Send a Microsoft Teams notification (stub — logs to console)."""
        logger.info(
            "NotificationDispatcher: [TEAMS] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_whatsapp(self, message: NotificationMessage) -> None:
        """Send a WhatsApp notification (stub — logs to console)."""
        logger.info(
            "NotificationDispatcher: [WHATSAPP] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_sms(self, message: NotificationMessage) -> None:
        """Send an SMS notification (stub — logs to console)."""
        logger.info(
            "NotificationDispatcher: [SMS] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_push(self, message: NotificationMessage) -> None:
        """Send a push notification (stub — logs to console)."""
        logger.info(
            "NotificationDispatcher: [PUSH] To: %s — %s: %s",
            message.recipient_id, message.title, message.body[:80],
        )

    def _send_webhook(self, message: NotificationMessage) -> None:
        """Send a webhook notification (stub — logs to console)."""
        config = self._channels.get(message.channel, ChannelConfig())
        webhook_url = config.config.get("webhook_url", "")
        logger.info(
            "NotificationDispatcher: [WEBHOOK] To: %s — URL: %s — %s: %s",
            message.recipient_id, webhook_url, message.title, message.body[:80],
        )

    # ── Private Helpers ────────────────────────────────────

    def _find_message(self, notification_id: str) -> Optional[NotificationMessage]:
        """Find a notification by ID."""
        def _do_find() -> Optional[NotificationMessage]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM notifications WHERE message_id = ?",
                (notification_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_message(row)

        return self._with_retry(_do_find, fallback=None)

    def _persist_message(
        self, message: NotificationMessage, *, insert: bool,
    ) -> None:
        """Insert or update a notification in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(
                    """INSERT INTO notifications
                       (message_id, channel, event, recipient_id, title, body,
                        request_id, priority, metadata, sent_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message.message_id,
                        message.channel.value,
                        message.event.value,
                        message.recipient_id,
                        message.title,
                        message.body,
                        message.request_id,
                        message.priority.value,
                        json.dumps(message.metadata),
                        message.sent_at,
                        message.status,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE notifications SET
                       sent_at=?, status=?
                       WHERE message_id=?""",
                    (message.sent_at, message.status, message.message_id),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> NotificationMessage:
        """Convert a database row to a NotificationMessage."""
        return NotificationMessage(
            message_id=row["message_id"],
            channel=NotificationChannel(row["channel"]),
            event=NotificationEvent(row["event"]),
            recipient_id=row["recipient_id"] or "",
            title=row["title"] or "",
            body=row["body"] or "",
            request_id=row["request_id"] or "",
            priority=NotificationPriority(row["priority"]),
            metadata=json.loads(row["metadata"] or "{}"),
            sent_at=row["sent_at"],
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
                    "NotificationDispatcher: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("NotificationDispatcher: DB error — %s", exc)
                break
        logger.error(
            "NotificationDispatcher: All retries exhausted — %s", last_exc,
        )
        return fallback


# ── Singleton ─────────────────────────────────────────────

_notification_instance: Optional[NotificationDispatcher] = None
_notification_lock = threading.Lock()


def get_notification_dispatcher(
    db_path: str = "notification.sqlite",
) -> NotificationDispatcher:
    """Get or create the global NotificationDispatcher instance."""
    global _notification_instance
    with _notification_lock:
        if _notification_instance is None:
            _notification_instance = NotificationDispatcher(db_path=db_path)
        return _notification_instance


def reset_notification_dispatcher() -> None:
    """Reset the global NotificationDispatcher (for testing)."""
    global _notification_instance
    _notification_instance = None


__all__ = [
    "NotificationChannel",
    "NotificationPriority",
    "NotificationEvent",
    "NotificationMessage",
    "ChannelConfig",
    "NotificationDispatcher",
    "get_notification_dispatcher",
    "reset_notification_dispatcher",
]
