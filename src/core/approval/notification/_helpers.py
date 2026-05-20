"""Helper methods extracted from notification."""

from __future__ import annotations

import json
import sqlite3
from ._types import NotificationChannel, NotificationEvent, NotificationPriority, NotificationMessage, ChannelConfig

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _init_db(self) -> None:
        """Create the notifications and channel_config tables."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
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
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_notification_request
                ON notifications(request_id, channel)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_notification_recipient
                ON notifications(recipient_id, status)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
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


    def _load_channel_configs(self) -> None:
        """Load channel configurations from the database."""
        def _do_load() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE notifications SET
                       sent_at=?, status=?
                       WHERE message_id=?""",
                    (message.sent_at, message.status, message.message_id),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)


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

