"""ZENIC-AGENTS - Channel Formatter

Re-exports all formatting functions and classes.
"""

from ._limits import PlatformLimits, LIMITS
from ._text import truncate, split_message, sanitize_plain_text, sanitize_html
from ._helpers import _store_and_replace, _parse_color
from ._wrapper import MessageFormatter
from ._telegram import escape_telegram_markdown_v2, format_telegram_message, build_telegram_inline_keyboard
from ._discord import build_discord_embed, build_discord_confirmation_components, format_discord_message
from ._slack import escape_slack_text, build_slack_blocks, build_slack_confirmation_blocks, format_slack_message
from ._teams import build_teams_adaptive_card, build_teams_confirmation_card, format_teams_message
from ._whatsapp import format_whatsapp_text, build_whatsapp_interactive_buttons
from ._sms import format_sms_text
from ._email import format_email_html, format_email_confirmation_html
from ._push import format_push_payload, format_push_confirmation_payload

__all__ = [
    "PlatformLimits", "LIMITS", "MessageFormatter",
    "truncate", "split_message", "sanitize_plain_text", "sanitize_html",
    "escape_telegram_markdown_v2", "format_telegram_message",
    "build_telegram_inline_keyboard",
    "build_discord_embed", "build_discord_confirmation_components",
    "format_discord_message",
    "escape_slack_text", "build_slack_blocks",
    "build_slack_confirmation_blocks", "format_slack_message",
    "build_teams_adaptive_card", "build_teams_confirmation_card",
    "format_teams_message",
    "format_whatsapp_text", "build_whatsapp_interactive_buttons",
    "format_sms_text",
    "format_email_html", "format_email_confirmation_html",
    "format_push_payload", "format_push_confirmation_payload",
]
