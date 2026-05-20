"""ZENIC-AGENTS - Channel Formatter: Discord"""

from __future__ import annotations

from typing import Any, Dict, List

from ._helpers import _parse_color
from ._limits import LIMITS
from ._text import truncate, sanitize_plain_text, sanitize_html
from .._types import ChannelMessage, ConfirmationRequest


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
    custom_id_prefix: str = "confirm",
) -> List[Dict[str, Any]]:
    """Build Discord Select Menu / Button components for confirmation.

    Args:
        request: The confirmation request with options.
        custom_id_prefix: Prefix for custom_id values.

    Returns:
        List of Discord component dicts (action rows).
    """
    buttons: List[Dict[str, Any]] = []
    for option in request.options:
        label = option.replace("_", " ").title()
        buttons.append({
            "type": 2,  # Button
            "style": 1,  # Primary
            "label": label,
            "custom_id": f"{custom_id_prefix}:{request.action_id}:{option}",
        })

    return [{"type": 1, "components": buttons}]


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
