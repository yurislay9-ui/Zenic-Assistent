"""notification — Core implementation."""

from __future__ import annotations

from ._types import *  # noqa: F403
from ._helpers import _init_db, _load_channel_configs, _persist_channel_config, _send_in_app, _send_email, _send_slack, _send_teams, _send_whatsapp, _send_sms, _send_push, _send_webhook, _find_message, _persist_message, _row_to_message, _with_retry

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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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

    @staticmethod
    @staticmethod