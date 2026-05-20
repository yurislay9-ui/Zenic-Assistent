"""
ZENIC-AGENTS — Channel Type Definitions

Canonical types for the unified channel system.
Every channel provider receives and returns these types — no channel-specific
leaky abstractions.  All cross-channel operations (routing, fallback, confirmation)
operate exclusively on these structures.

Design invariants:
  1. No channel-specific fields leak into the base types.
  2. All datetimes are unix timestamps (float) — no datetime objects.
  3. All text fields are str — no bytes.
  4. Optional fields default to None/empty — never raise on missing data.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


# ──────────────────────────────────────────────────────────────
#  CHANNEL CAPABILITIES
# ──────────────────────────────────────────────────────────────

class ChannelCapability(str, enum.Enum):
    """What a channel provider can do.

    Used by ChannelRouter to pick the right channel for a task
    and by AdapterRegistry to query providers by capability.
    """
    SEND_TEXT = "send_text"
    SEND_RICH = "send_rich"            # Markdown, embeds, cards, blocks
    SEND_CONFIRMATION = "send_confirmation"  # Interactive buttons/keyboards
    SEND_FILE = "send_file"            # Attachments, media
    RECEIVE_MESSAGE = "receive_message"     # Inbound (bidirectional)
    RECEIVE_CONFIRMATION = "receive_confirmation"  # Callback responses
    SEND_HTML = "send_html"            # Email-like HTML body
    SEND_SMS = "send_sms"              # Plain SMS
    SEND_MMS = "send_mms"              # SMS with media
    SEND_PUSH = "send_push"            # Web/mobile push notifications
    THREAD = "thread"                  # Thread/conversation support
    REPLY = "reply"                    # Reply-to-message support


class ChannelPriority(str, enum.Enum):
    """Message priority levels — maps to ChannelRouter priority ranges."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class DeliveryStatus(str, enum.Enum):
    """Delivery status for a single channel send attempt."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    FALLBACK = "fallback"             # Sent via fallback channel
    DRY_RUN = "dry_run"               # Not actually sent (dry-run mode)


# ──────────────────────────────────────────────────────────────
#  MESSAGE TYPES
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChannelMessage:
    """Universal message envelope — the ONLY input type for channel.send().

    Every field is optional because channels have different capabilities.
    The provider picks the fields it supports and ignores the rest.
    """
    text: str = ""
    subject: str = ""
    html: str = ""                     # HTML body (email, Teams cards)
    recipient: str = ""                # Single recipient (chat_id, email, phone)
    recipients: Sequence[str] = ()     # Multiple recipients
    reply_to: str = ""                 # Message ID to reply to
    thread_id: str = ""                # Thread/conversation ID
    priority: ChannelPriority = ChannelPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Rich content — provider interprets per-platform
    title: str = ""                    # Embed title, card header, etc.
    subtitle: str = ""                 # Secondary title
    color: str = ""                    # Embed/card color (hex or name)
    footer: str = ""                   # Embed footer text
    image_url: str = ""                # Main image
    thumbnail_url: str = ""            # Thumbnail image
    fields: Sequence[Dict[str, str]] = ()  # Key-value pairs [{title, value, inline}]
    file_url: str = ""                 # File attachment URL
    file_name: str = ""                # File attachment name

    def __post_init__(self) -> None:
        """Validate invariant: at least one content field must be set."""
        if not self.text and not self.html and not self.file_url:
            object.__setattr__(self, "text", " ")  # Ensure non-empty


@dataclass(frozen=True)
class ChannelResponse:
    """Universal response from a channel send operation.

    Every provider returns this — no exceptions, no channel-specific types.
    """
    success: bool
    channel: str                       # Provider name that handled it
    message_id: str = ""               # Platform message ID (if available)
    status: DeliveryStatus = DeliveryStatus.SENT
    error: str = ""                    # Error message if failed
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0            # Unix timestamp of delivery

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for logging/audit."""
        return {
            "success": self.success,
            "channel": self.channel,
            "message_id": self.message_id,
            "status": self.status.value,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


# ──────────────────────────────────────────────────────────────
#  CONFIRMATION TYPES
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConfirmationRequest:
    """Request for user confirmation via interactive UI elements.

    Maps to:
      - Telegram: inline_keyboard with callback buttons
      - Discord: button components
      - Slack: Block Kit with button elements
      - Teams: ActionCard with actions
      - WhatsApp: interactive button/template
      - SMS: reply with YES/NO
    """
    action_id: str
    action_type: str
    title: str                         # Confirmation prompt title
    message: str                       # Detailed message
    options: Sequence[str] = ("yes", "no", "more_info")
    timeout_seconds: int = 300         # 5 minutes default
    channel: str = ""                  # Target channel
    recipient: str = ""                # Target user/chat
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmationResult:
    """Result of a user's response to a confirmation request."""
    action_id: str
    response: str                      # "yes", "no", "more_info", or custom
    confirmed: bool
    responder_id: str = ""             # User who responded
    channel: str = ""                  # Channel that received the response
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
#  PROVIDER CONFIG
# ──────────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """Configuration for a channel provider.

    Loaded from environment variables, YAML, or passed programmatically.
    Each provider subclass defines its own required_fields.
    """
    enabled: bool = True
    webhook_url: str = ""
    api_url: str = ""
    bot_token: str = ""
    phone_number: str = ""
    account_sid: str = ""
    auth_token: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_configured(self) -> bool:
        """Check if at least one connection method is configured."""
        return bool(self.webhook_url or self.api_url or self.bot_token)


# ──────────────────────────────────────────────────────────────
#  RATE LIMIT INFO
# ──────────────────────────────────────────────────────────────

@dataclass
class RateLimitInfo:
    """Rate limit status for a channel provider."""
    remaining: int = -1                # -1 = unknown/unlimited
    reset_at: float = 0.0             # Unix timestamp when limit resets
    limit: int = -1                    # Total limit per window (-1 = unknown)

    @property
    def is_limited(self) -> bool:
        """Check if currently rate limited."""
        return self.remaining == 0

    @property
    def is_unknown(self) -> bool:
        """Check if rate limit info is unavailable."""
        return self.remaining < 0


# ──────────────────────────────────────────────────────────────
#  HANDLER TYPE ALIASES
# ──────────────────────────────────────────────────────────────

from typing import Awaitable, Callable

# Inbound message handler: receives ChannelMessage, returns ChannelResponse
MessageHandler = Callable[[ChannelMessage], Awaitable[ChannelResponse]]

# Inbound confirmation handler: receives ConfirmationResult, returns arbitrary dict
ConfirmationHandler = Callable[[ConfirmationResult], Awaitable[Dict[str, Any]]]


# ──────────────────────────────────────────────────────────────
#  PUBLIC EXPORTS
# ──────────────────────────────────────────────────────────────

__all__ = [
    "ChannelCapability",
    "ChannelPriority",
    "DeliveryStatus",
    "ChannelMessage",
    "ChannelResponse",
    "ConfirmationRequest",
    "ConfirmationResult",
    "ProviderConfig",
    "RateLimitInfo",
    "MessageHandler",
    "ConfirmationHandler",
]
