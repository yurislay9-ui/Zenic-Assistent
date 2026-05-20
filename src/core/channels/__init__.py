"""
ZENIC-AGENTS — Unified Channel System

Phase 0: Infrastructure (ChannelProvider protocol, AdapterRegistry, ChannelRouter, MessageFormatter)
Phase 1: Providers (Teams, Slack, WhatsApp, Twilio SMS)
Phase 2: Providers (Email, Push Notifications)

Architecture:
  - ChannelProvider protocol → every provider implements the same interface
  - AdapterRegistry → dynamic registration + fallback routing (mirrors ExecutorRegistry)
  - ChannelRouter → priority-based routing with user preferences
  - MessageFormatter → cross-platform formatting (Markdown, embeds, cards, blocks)
  - LogChannelProvider → always-available terminal fallback
"""

# ── Phase 0: Core Infrastructure ──────────────────────────────

# Types
from ._types import (
    ChannelCapability,
    ChannelPriority,
    DeliveryStatus,
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    ConfirmationResult,
    ProviderConfig,
    RateLimitInfo,
    MessageHandler,
    ConfirmationHandler,
)

# Protocol
from ._protocol import (
    ChannelProvider,
    InboundChannelProvider,
    has_capability,
    requires_inbound,
    can_send_confirmation,
)

# Formatter
from ._formatter import (
    PlatformLimits,
    LIMITS,
    MessageFormatter,
    truncate,
    split_message,
    sanitize_plain_text,
    sanitize_html,
    escape_telegram_markdown_v2,
    format_telegram_message,
    build_telegram_inline_keyboard,
    build_discord_embed,
    build_discord_confirmation_components,
    format_discord_message,
    escape_slack_text,
    build_slack_blocks,
    build_slack_confirmation_blocks,
    format_slack_message,
    build_teams_adaptive_card,
    build_teams_confirmation_card,
    format_teams_message,
    format_whatsapp_text,
    build_whatsapp_interactive_buttons,
    format_sms_text,
    # Email
    format_email_html,
    format_email_confirmation_html,
    # Push
    format_push_payload,
    format_push_confirmation_payload,
)

# Registry + Router
from ._registry import (
    AdapterRegistry,
    ChannelRouter,
    get_default_registry,
    get_default_router,
    reset_default_registry,
)

# Log Provider (always available)
from ._log_provider import LogChannelProvider

# ── Phase 1: Channel Providers ────────────────────────────────

from .providers.teams import TeamsChannelProvider
from .providers.slack import SlackChannelProvider
from .providers.whatsapp import WhatsAppChannelProvider
from .providers.twilio_sms import TwilioSMSChannelProvider
from .providers.push import PushChannelProvider
from .providers.email import EmailChannelProvider


__all__ = [
    # Types
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
    # Protocol
    "ChannelProvider",
    "InboundChannelProvider",
    "has_capability",
    "requires_inbound",
    "can_send_confirmation",
    # Formatter
    "PlatformLimits",
    "LIMITS",
    "MessageFormatter",
    "truncate",
    "split_message",
    "sanitize_plain_text",
    "sanitize_html",
    "escape_telegram_markdown_v2",
    "format_telegram_message",
    "build_telegram_inline_keyboard",
    "build_discord_embed",
    "build_discord_confirmation_components",
    "format_discord_message",
    "escape_slack_text",
    "build_slack_blocks",
    "build_slack_confirmation_blocks",
    "format_slack_message",
    "build_teams_adaptive_card",
    "build_teams_confirmation_card",
    "format_teams_message",
    "format_whatsapp_text",
    "build_whatsapp_interactive_buttons",
    "format_sms_text",
    # Email
    "format_email_html",
    "format_email_confirmation_html",
    # Push
    "format_push_payload",
    "format_push_confirmation_payload",
    # Registry + Router
    "AdapterRegistry",
    "ChannelRouter",
    "get_default_registry",
    "get_default_router",
    "reset_default_registry",
    # Providers
    "LogChannelProvider",
    "TeamsChannelProvider",
    "SlackChannelProvider",
    "WhatsAppChannelProvider",
    "TwilioSMSChannelProvider",
    # Phase 2
    "EmailChannelProvider",
    "PushChannelProvider",
]
