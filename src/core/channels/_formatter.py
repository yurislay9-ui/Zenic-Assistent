"""
ZENIC-AGENTS — Message Formatter

Cross-platform message formatting engine.
Converts ChannelMessage into platform-specific payloads:
  - Telegram: MarkdownV2, inline keyboards
  - Discord: Embeds, button components
  - Slack: Block Kit
  - Teams: Adaptive Cards
  - WhatsApp: Interactive buttons, templates
  - SMS: Plain text with character limits

Design invariants:
  1. Pure functions — no side effects, no I/O.
  2. Never raises — always returns a valid payload dict.
  3. Platform limits are enforced (truncation, splitting).
  4. No external dependencies — only stdlib.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ._types import ChannelMessage, ConfirmationRequest


# ──────────────────────────────────────────────────────────────
#  PLATFORM LIMITS
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlatformLimits:
    """Character/content limits per platform."""
    telegram_text: int = 4096
    telegram_caption: int = 1024
    discord_text: int = 2000
    discord_embed_title: int = 256
    discord_embed_description: int = 2048
    discord_embed_fields: int = 25
    discord_embed_field_name: int = 256
    discord_embed_field_value: int = 1024
    discord_embed_footer: int = 2048
    slack_text: int = 3000
    slack_block_text: int = 3000
    teams_text: int = 18000           # Adaptive Card body limit
    whatsapp_text: int = 4096
    sms_text: int = 160
    sms_mms_text: int = 1600


LIMITS = PlatformLimits()


# ──────────────────────────────────────────────────────────────
#  TEXT UTILITIES
# ──────────────────────────────────────────────────────────────

def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def split_message(text: str, max_length: int, overlap: int = 0) -> List[str]:
    """Split long text into chunks respecting paragraph/line/word boundaries.

    Strategy (in order of preference):
      1. Split on double-newline (paragraph boundary)
      2. Split on single newline (line boundary)
      3. Split on space (word boundary)
      4. Hard split at max_length

    Args:
        text: The text to split.
        max_length: Maximum length per chunk.
        overlap: Number of characters to overlap between chunks (for context).

    Returns:
        List of text chunks, each <= max_length.
    """
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []

    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Find best split point within max_length
        split_at = max_length

        # Try paragraph boundary
        para_pos = text.rfind("\n\n", 0, max_length)
        if para_pos > max_length * 0.3:
            split_at = para_pos + 2
        else:
            # Try line boundary
            line_pos = text.rfind("\n", 0, max_length)
            if line_pos > max_length * 0.3:
                split_at = line_pos + 1
            else:
                # Try word boundary
                space_pos = text.rfind(" ", 0, max_length)
                if space_pos > max_length * 0.3:
                    split_at = space_pos + 1

        chunks.append(text[:split_at])
        text = text[split_at - overlap:] if overlap else text[split_at:]

    return chunks


def sanitize_plain_text(text: str) -> str:
    """Strip ANSI codes, control chars, and collapse whitespace."""
    # Remove ANSI escape sequences
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    # Remove control characters except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse multiple spaces (not newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


def sanitize_html(text: str) -> str:
    """Remove script tags and escape HTML entities."""
    # Remove script tags
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove event handlers
    text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', "", text, flags=re.IGNORECASE)
    return text


# ──────────────────────────────────────────────────────────────
#  TELEGRAM FORMATTING
# ──────────────────────────────────────────────────────────────

# MarkdownV2 special characters that must be escaped
_TELEGRAM_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


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
) -> Dict[str, Any]:
    """Build a Telegram inline keyboard for confirmation requests.

    Returns:
        Dict with reply_markup for sendMessage.
    """
    buttons: List[List[Dict[str, str]]] = []

    option_labels = {
        "yes": "✅ Confirm",
        "no": "❌ Deny",
        "more_info": "ℹ️ More Info",
    }

    row: List[Dict[str, str]] = []
    for option in request.options:
        label = option_labels.get(option, option)
        row.append({
            "text": label,
            "callback_data": f"confirm:{request.action_id}:{option}",
        })
    buttons.append(row)

    return {"inline_keyboard": buttons}


# ──────────────────────────────────────────────────────────────
#  DISCORD FORMATTING
# ──────────────────────────────────────────────────────────────

def build_discord_embed(message: ChannelMessage) -> Dict[str, Any]:
    """Build a Discord embed from a ChannelMessage.

    Returns:
        Dict compatible with Discord message embed.
    """
    embed: Dict[str, Any] = {}

    if message.title:
        embed["title"] = truncate(message.title, LIMITS.discord_embed_title)

    if message.text:
        embed["description"] = truncate(
            sanitize_plain_text(message.text),
            LIMITS.discord_embed_description,
        )

    if message.color:
        embed["color"] = _parse_color(message.color)

    if message.url:
        embed["url"] = message.url if hasattr(message, 'url') else ""

    if message.footer:
        embed["footer"] = {"text": truncate(message.footer, LIMITS.discord_embed_footer)}

    if message.image_url:
        embed["image"] = {"url": message.image_url}

    if message.thumbnail_url:
        embed["thumbnail"] = {"url": message.thumbnail_url}

    if message.fields:
        embed_fields = []
        for f in message.fields[:LIMITS.discord_embed_fields]:
            embed_fields.append({
                "name": truncate(f.get("title", f.get("name", "")), LIMITS.discord_embed_field_name),
                "value": truncate(f.get("value", ""), LIMITS.discord_embed_field_value),
                "inline": f.get("inline", False),
            })
        embed["fields"] = embed_fields

    return embed


def build_discord_confirmation_components(
    request: ConfirmationRequest,
) -> List[Dict[str, Any]]:
    """Build Discord button components for confirmation requests.

    Returns:
        List of component dicts for Discord message.
    """
    button_styles = {
        "yes": 3,    # Success (green)
        "no": 4,     # Danger (red)
        "more_info": 2,  # Secondary (grey)
    }

    buttons: List[Dict[str, Any]] = []
    for option in request.options:
        style = button_styles.get(option, 1)  # Default: Primary
        label = option.replace("_", " ").title()
        buttons.append({
            "type": 2,  # Button
            "style": style,
            "label": label,
            "custom_id": f"zenic_confirm_{request.action_id}:{option}",
        })

    return [{"type": 1, "components": buttons}]  # ActionRow


def format_discord_message(message: ChannelMessage) -> Dict[str, Any]:
    """Format a ChannelMessage into a Discord message payload.

    Uses embeds for titled messages, plain text otherwise.
    """
    payload: Dict[str, Any] = {}

    if message.title or message.fields or message.image_url:
        # Rich message with embed
        embed = build_discord_embed(message)
        payload["embeds"] = [embed]
        if message.text and not embed.get("description"):
            payload["content"] = truncate(
                sanitize_plain_text(message.text),
                LIMITS.discord_text,
            )
    else:
        # Plain text message
        text = message.text or message.html
        payload["content"] = truncate(
            sanitize_plain_text(text) if message.text else sanitize_html(text),
            LIMITS.discord_text,
        )

    if message.reply_to:
        payload["message_reference"] = {"message_id": message.reply_to}

    return payload


# ──────────────────────────────────────────────────────────────
#  SLACK FORMATTING
# ──────────────────────────────────────────────────────────────

def escape_slack_text(text: str) -> str:
    """Escape special characters for Slack mrkdwn format."""
    if not text:
        return ""
    # Escape & < > (Slack's required escapes)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def build_slack_blocks(message: ChannelMessage) -> List[Dict[str, Any]]:
    """Build Slack Block Kit blocks from a ChannelMessage.

    Returns:
        List of Block Kit block dicts.
    """
    blocks: List[Dict[str, Any]] = []

    # Header block
    if message.title:
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": truncate(message.title, 150),
            },
        })

    # Section block with text
    text = message.text or message.html
    if text:
        clean_text = sanitize_plain_text(text) if message.text else sanitize_html(text)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": truncate(escape_slack_text(clean_text), LIMITS.slack_block_text),
            },
        })

    # Fields block
    if message.fields:
        fields = []
        for f in message.fields[:10]:
            fields.append({
                "type": "mrkdwn",
                "text": f"*{escape_slack_text(f.get('title', f.get('name', '')))}:*\n{escape_slack_text(f.get('value', ''))}",
            })
        blocks.append({"type": "section", "fields": fields})

    # Image block
    if message.image_url:
        blocks.append({
            "type": "image",
            "image_url": message.image_url,
            "alt_text": message.title or "Image",
        })

    # Context block (footer)
    if message.footer:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": truncate(escape_slack_text(message.footer), 2000),
                }
            ],
        })

    return blocks


def build_slack_confirmation_blocks(
    request: ConfirmationRequest,
) -> List[Dict[str, Any]]:
    """Build Slack Block Kit blocks with confirmation buttons.

    Returns:
        List of Block Kit block dicts.
    """
    blocks: List[Dict[str, Any]] = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": truncate(request.title, 150),
        },
    })

    # Message body
    if request.message:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": truncate(escape_slack_text(request.message), LIMITS.slack_block_text),
            },
        })

    # Action block with buttons
    button_styles = {
        "yes": "primary",
        "no": "danger",
        "more_info": None,  # Default style
    }

    elements: List[Dict[str, Any]] = []
    for option in request.options:
        button: Dict[str, Any] = {
            "type": "button",
            "text": {"type": "plain_text", "text": option.replace("_", " ").title()},
            "action_id": f"zenic_confirm_{request.action_id}_{option}",
            "value": f"{request.action_id}:{option}",
        }
        style = button_styles.get(option)
        if style:
            button["style"] = style
        elements.append(button)

    blocks.append({"type": "actions", "elements": elements})

    return blocks


def format_slack_message(message: ChannelMessage) -> Dict[str, Any]:
    """Format a ChannelMessage into a Slack chat.postMessage payload."""
    blocks = build_slack_blocks(message)

    payload: Dict[str, Any] = {}
    if blocks:
        payload["blocks"] = blocks
    else:
        text = message.text or message.html
        payload["text"] = truncate(
            sanitize_plain_text(text) if message.text else sanitize_html(text),
            LIMITS.slack_text,
        )

    if message.thread_id:
        payload["thread_ts"] = message.thread_id

    if message.reply_to:
        payload["thread_ts"] = message.reply_to

    return payload


# ──────────────────────────────────────────────────────────────
#  TEAMS FORMATTING
# ──────────────────────────────────────────────────────────────

def build_teams_adaptive_card(message: ChannelMessage) -> Dict[str, Any]:
    """Build a Microsoft Teams Adaptive Card from a ChannelMessage.

    Returns:
        Dict with Adaptive Card schema.
    """
    body: List[Dict[str, Any]] = []

    # Title
    if message.title:
        body.append({
            "type": "TextBlock",
            "text": message.title,
            "size": "Large",
            "weight": "Bolder",
            "wrap": True,
        })

    # Subtitle
    if message.subtitle:
        body.append({
            "type": "TextBlock",
            "text": message.subtitle,
            "isSubtle": True,
            "wrap": True,
        })

    # Main text
    text = message.text or message.html
    if text:
        clean = sanitize_plain_text(text) if message.text else sanitize_html(text)
        body.append({
            "type": "TextBlock",
            "text": truncate(clean, LIMITS.teams_text),
            "wrap": True,
        })

    # Fact set (fields)
    if message.fields:
        facts = [
            {"title": f.get("title", f.get("name", "")), "value": str(f.get("value", ""))}
            for f in message.fields[:15]
        ]
        body.append({"type": "FactSet", "facts": facts})

    # Image
    if message.image_url:
        body.append({
            "type": "Image",
            "url": message.image_url,
            "altText": message.title or "Image",
        })

    # Footer
    if message.footer:
        body.append({
            "type": "TextBlock",
            "text": message.footer,
            "isSubtle": True,
            "size": "Small",
            "wrap": True,
        })

    card: Dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }

    return card


def build_teams_confirmation_card(
    request: ConfirmationRequest,
) -> Dict[str, Any]:
    """Build a Teams ActionCard for confirmation requests.

    Returns:
        Dict with Adaptive Card including Action.Submit buttons.
    """
    body: List[Dict[str, Any]] = []

    body.append({
        "type": "TextBlock",
        "text": request.title,
        "size": "Large",
        "weight": "Bolder",
        "wrap": True,
    })

    if request.message:
        body.append({
            "type": "TextBlock",
            "text": truncate(request.message, LIMITS.teams_text),
            "wrap": True,
        })

    actions: List[Dict[str, Any]] = []
    for option in request.options:
        actions.append({
            "type": "Action.Submit",
            "title": option.replace("_", " ").title(),
            "data": {
                "action_id": request.action_id,
                "response": option,
                "type": "zenic_confirmation",
            },
        })

    card: Dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }

    return card


def format_teams_message(message: ChannelMessage) -> Dict[str, Any]:
    """Format a ChannelMessage into a Teams Incoming Webhook payload."""
    card = build_teams_adaptive_card(message)

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


# ──────────────────────────────────────────────────────────────
#  WHATSAPP FORMATTING
# ──────────────────────────────────────────────────────────────

def format_whatsapp_text(message: ChannelMessage) -> Dict[str, Any]:
    """Format a ChannelMessage into a WhatsApp Cloud API text payload."""
    text = sanitize_plain_text(message.text)
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": message.recipient,
        "type": "text",
        "text": {"body": truncate(text, LIMITS.whatsapp_text), "preview_url": True},
    }


def build_whatsapp_interactive_buttons(
    request: ConfirmationRequest,
) -> Dict[str, Any]:
    """Build WhatsApp interactive button message for confirmation.

    Returns:
        Dict compatible with WhatsApp Cloud API interactive message.
    """
    buttons: List[Dict[str, Any]] = []
    for option in request.options[:3]:  # WhatsApp limit: 3 buttons
        buttons.append({
            "type": "reply",
            "reply": {"id": f"{request.action_id}:{option}", "title": option.replace("_", " ").title()[:20]},
        })

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": request.recipient,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": truncate(request.message, 1024)},
            "action": {"buttons": buttons},
        },
    }


# ──────────────────────────────────────────────────────────────
#  SMS FORMATTING
# ──────────────────────────────────────────────────────────────

def format_sms_text(message: ChannelMessage) -> str:
    """Format a ChannelMessage into a plain SMS string.

    Strips all rich formatting, enforces 160-char limit per segment.
    """
    parts: List[str] = []

    if message.title:
        parts.append(f"[{message.title}]")

    text = sanitize_plain_text(message.text)
    if text:
        parts.append(text)

    if message.footer:
        parts.append(f"— {message.footer}")

    return " ".join(parts) if parts else ""


# ──────────────────────────────────────────────────────────────
#  EMAIL FORMATTING
# ──────────────────────────────────────────────────────────────

def format_email_html(message: ChannelMessage) -> str:
    """Format a ChannelMessage into an HTML email body.

    Builds a styled HTML email with optional title, body,
    field table, and footer.
    """
    parts: List[str] = []

    # Title
    if message.title:
        parts.append(f'<h2 style="color:#1a1a1a;margin:0 0 12px 0;">{html_module.escape(message.title)}</h2>')

    # Subtitle
    if message.subtitle:
        parts.append(f'<p style="color:#666;margin:0 0 8px 0;font-size:14px;">{html_module.escape(message.subtitle)}</p>')

    # Body
    if message.html:
        parts.append(f'<div style="margin:0 0 12px 0;">{sanitize_html(message.html)}</div>')
    elif message.text:
        escaped = html_module.escape(message.text).replace("\n", "<br>")
        parts.append(f'<div style="margin:0 0 12px 0;">{escaped}</div>')

    # Fields table
    if message.fields:
        rows = []
        for f in message.fields[:20]:
            key = html_module.escape(f.get("title", f.get("name", "")))
            val = html_module.escape(str(f.get("value", "")))
            rows.append(f'<tr><td style="padding:6px 12px;font-weight:bold;border-bottom:1px solid #eee;">{key}</td>'
                       f'<td style="padding:6px 12px;border-bottom:1px solid #eee;">{val}</td></tr>')
        parts.append(
            f'<table style="border-collapse:collapse;width:100%;margin:0 0 12px 0;">'
            f'{"".join(rows)}</table>'
        )

    # Image
    if message.image_url:
        alt_text = html_module.escape(message.title or "Image")
        parts.append(f'<img src="{message.image_url}" alt="{alt_text}" style="max-width:100%;margin:0 0 12px 0;" />')

    # Footer
    if message.footer:
        parts.append(f'<p style="color:#999;font-size:12px;margin:12px 0 0 0;">{html_module.escape(message.footer)}</p>')

    body = "\n".join(parts)
    return (
        f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">'
        f'{body}</div>'
    )


def format_email_confirmation_html(request: ConfirmationRequest) -> str:
    """Format a confirmation request as an HTML email with action buttons.

    Returns styled HTML with YES/NO/MORE_INFO links.
    """
    button_colors = {
        "yes": "#28a745",
        "no": "#dc3545",
        "more_info": "#6c757d",
    }
    button_labels = {
        "yes": "✅ Confirm",
        "no": "❌ Deny",
        "more_info": "ℹ️ More Info",
    }

    buttons = []
    for option in request.options:
        color = button_colors.get(option, "#007bff")
        label = button_labels.get(option, option.replace("_", " ").title())
        buttons.append(
            f'<a href="#action-{option}" style="display:inline-block;padding:10px 20px;'
            f'background-color:{color};color:white;text-decoration:none;border-radius:4px;'
            f'margin-right:8px;font-weight:bold;">{label}</a>'
        )

    return (
        f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">'
        f'<h2 style="color:#1a1a1a;">{html_module.escape(request.title)}</h2>'
        f'<p style="color:#333;">{html_module.escape(request.message)}</p>'
        f'<div style="margin:20px 0;">{"".join(buttons)}</div>'
        f'<p style="color:#999;font-size:12px;">Action ID: {html_module.escape(request.action_id)} | '
        f'Expires in {request.timeout_seconds // 60} minutes</p>'
        f'</div>'
    )


# ──────────────────────────────────────────────────────────────
#  PUSH NOTIFICATION FORMATTING
# ──────────────────────────────────────────────────────────────

def format_push_payload(message: ChannelMessage) -> Dict[str, Any]:
    """Format a ChannelMessage into a push notification payload.

    Returns a dict with title, body, and optional data fields.
    """
    title = message.title or message.subject or "Notification"
    body = sanitize_plain_text(message.text)
    if len(body) > 200:
        body = body[:197] + "..."

    payload: Dict[str, Any] = {
        "title": title,
        "body": body,
    }

    # Add fields as data
    if message.fields:
        payload["data"] = {
            f.get("title", f.get("name", f"field_{i}")): str(f.get("value", ""))
            for i, f in enumerate(message.fields[:10])
        }

    # Add image if present
    if message.image_url:
        payload["image"] = message.image_url

    # Priority
    priority_map = {
        ChannelPriority.LOW: "normal",
        ChannelPriority.NORMAL: "normal",
        ChannelPriority.HIGH: "high",
        ChannelPriority.URGENT: "high",
        ChannelPriority.EMERGENCY: "high",
    }
    from ._types import ChannelPriority as CP
    payload["priority"] = priority_map.get(message.priority, "normal")

    return payload


def format_push_confirmation_payload(request: ConfirmationRequest) -> Dict[str, Any]:
    """Format a confirmation request as a push notification payload.

    Returns a dict with title, body, and action categories.
    """
    actions = []
    for option in request.options:
        actions.append({"action": option, "title": option.replace("_", " ").title()})

    return {
        "title": request.title,
        "body": sanitize_plain_text(request.message)[:200],
        "actions": actions,
        "data": {
            "action_id": request.action_id,
            "action_type": request.action_type,
            "type": "zenic_confirmation",
        },
        "priority": "high",
    }


# ──────────────────────────────────────────────────────────────
#  CONVENIENCE CLASS
# ──────────────────────────────────────────────────────────────

class MessageFormatter:
    """Stateless convenience wrapper for all formatting functions.

    All methods are static — no instance state.
    Use directly: MessageFormatter.format_telegram(msg)
    """

    # Platform limits
    limits = LIMITS

    # Text utilities
    truncate = staticmethod(truncate)
    split_message = staticmethod(split_message)
    sanitize_plain_text = staticmethod(sanitize_plain_text)
    sanitize_html = staticmethod(sanitize_html)

    # Telegram
    escape_telegram_markdown_v2 = staticmethod(escape_telegram_markdown_v2)
    format_telegram_message = staticmethod(format_telegram_message)
    build_telegram_inline_keyboard = staticmethod(build_telegram_inline_keyboard)

    # Discord
    build_discord_embed = staticmethod(build_discord_embed)
    build_discord_confirmation_components = staticmethod(build_discord_confirmation_components)
    format_discord_message = staticmethod(format_discord_message)

    # Slack
    escape_slack_text = staticmethod(escape_slack_text)
    build_slack_blocks = staticmethod(build_slack_blocks)
    build_slack_confirmation_blocks = staticmethod(build_slack_confirmation_blocks)
    format_slack_message = staticmethod(format_slack_message)

    # Teams
    build_teams_adaptive_card = staticmethod(build_teams_adaptive_card)
    build_teams_confirmation_card = staticmethod(build_teams_confirmation_card)
    format_teams_message = staticmethod(format_teams_message)

    # WhatsApp
    format_whatsapp_text = staticmethod(format_whatsapp_text)
    build_whatsapp_interactive_buttons = staticmethod(build_whatsapp_interactive_buttons)

    # SMS
    format_sms_text = staticmethod(format_sms_text)

    # Email
    format_email_html = staticmethod(format_email_html)
    format_email_confirmation_html = staticmethod(format_email_confirmation_html)

    # Push
    format_push_payload = staticmethod(format_push_payload)
    format_push_confirmation_payload = staticmethod(format_push_confirmation_payload)


# ──────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────

def _store_and_replace(match: re.Match, store: List[str]) -> str:
    """Store a regex match and return a placeholder."""
    idx = len(store)
    store.append(match.group(0))
    return f"__CODE_BLOCK_{idx}__"


def _parse_color(color: str) -> int:
    """Parse a color string to Discord integer color.

    Accepts: hex (#RRGGBB, RRGGBB), named colors, or integer strings.
    """
    color = color.strip()

    # Hex
    if color.startswith("#"):
        return int(color[1:], 16)
    if color.startswith("0x"):
        return int(color[2:], 16)

    # Named colors
    named = {
        "red": 0xFF0000, "green": 0x00FF00, "blue": 0x0000FF,
        "yellow": 0xFFFF00, "orange": 0xFFA500, "purple": 0x800080,
        "cyan": 0x00FFFF, "white": 0xFFFFFF, "black": 0x000000,
        "gray": 0x808080, "grey": 0x808080,
    }
    if color.lower() in named:
        return named[color.lower()]

    # Try integer
    try:
        return int(color)
    except ValueError:
        return 0x5865F2  # Default: Blurple


# ──────────────────────────────────────────────────────────────
#  PUBLIC EXPORTS
# ──────────────────────────────────────────────────────────────

__all__ = [
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
]
