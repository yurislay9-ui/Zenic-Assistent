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

from ._templates import (
    ChannelConfig,
    NotificationChannel,
    NotificationEvent,
    NotificationMessage,
    NotificationPriority,
)
from ._notifier import (
    NotificationDispatcher,
    get_notification_dispatcher,
    reset_notification_dispatcher,
)

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
