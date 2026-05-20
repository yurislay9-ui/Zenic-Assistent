"""ZENIC-AGENTS - Channel Formatter: WhatsApp"""

from __future__ import annotations

from typing import Any, Dict, List

from ._limits import LIMITS
from ._text import truncate, sanitize_plain_text
from .._types import ChannelMessage, ConfirmationRequest


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
    """Build a WhatsApp interactive button message for confirmation.

    Args:
        request: The confirmation request with options.

    Returns:
        Dict with WhatsApp interactive message payload.
    """
    buttons = []
    for i, option in enumerate(request.options[:3]):  # WhatsApp allows max 3 buttons
        label = option.replace("_", " ").title()
        buttons.append({
            "type": "reply",
            "reply": {"id": f"{request.action_id}:{option}", "title": label},
        })

    body_text = request.message or request.title or "Please confirm"

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": request.recipient,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": truncate(body_text, LIMITS.whatsapp_text)},
            "action": {"buttons": buttons},
        },
    }
