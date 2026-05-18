"""notification — Type definitions."""

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

