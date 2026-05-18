"""ZENIC-AGENTS - Channel Formatter: Telegram"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ._helpers import _store_and_replace, _parse_color
from ._limits import LIMITS
from ._text import truncate, sanitize_plain_text, sanitize_html
from .._types import ChannelMessage, ConfirmationRequest

# Characters that need escaping in Telegram MarkdownV2
_TELEGRAM_ESCAPE_CHARS = set("_*[]()~`>#+-=|{}.!")


def escape_telegram_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 format.

    Preserves code blocks (```...```) and inline code (`...`).
    """
    if not text:
        return ""

    # Protect code blocks
    code_blocks: List[str] = []
    protected = text

    # Protect triple backtick blocks
    protected = re.sub(
        r"```[\s\S]*?```",
        lambda m: _store_and_replace(m, code_blocks),
        protected,
    )
    # Protect inline code
    protected = re.sub(
        r"`[^`]+`",
        lambda m: _store_and_replace(m, code_blocks),
        protected,
    )

    # Escape special chars
    escaped = []
    for ch in protected:
        if ch in _TELEGRAM_ESCAPE_CHARS:
            escaped.append(f"\\{ch}")
        else:
            escaped.append(ch)

    result = "".join(escaped)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        result = result.replace(f"__CODE_BLOCK_{i}__", block)

    return result


def format_telegram_message(message: ChannelMessage) -> Dict[str, Any]:
    """Format a ChannelMessage into a Telegram Bot API payload.

    Returns:
        Dict compatible with sendMessage API call.
    """
    text = message.text or message.html
    text = sanitize_plain_text(text) if message.text else sanitize_html(text)

    payload: Dict[str, Any] = {
        "chat_id": message.recipient,
        "parse_mode": "MarkdownV2",
        "text": escape_telegram_markdown_v2(truncate(text, LIMITS.telegram_text)),
    }

    if message.reply_to:
        payload["reply_to_message_id"] = message.reply_to

    if message.thread_id:
        payload["message_thread_id"] = message.thread_id

    return payload


def build_telegram_inline_keyboard(
    request: ConfirmationRequest,
    callback_prefix: str = "confirm",
) -> Dict[str, Any]:
    """Build a Telegram InlineKeyboardMarkup for confirmation requests.

    Args:
        request: The confirmation request with options.
        callback_prefix: Prefix for callback_data values.

    Returns:
        Dict with inline_keyboard structure for Telegram Bot API.
    """
    buttons: List[Dict[str, str]] = []
    for option in request.options:
        label = option.replace("_", " ").title()
        buttons.append({
            "text": label,
            "callback_data": f"{callback_prefix}:{request.action_id}:{option}",
        })

    return {"inline_keyboard": [buttons]}
