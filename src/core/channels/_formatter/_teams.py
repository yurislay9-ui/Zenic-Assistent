"""ZENIC-AGENTS - Channel Formatter: Teams"""

from __future__ import annotations

from typing import Any, Dict, List

from ._limits import LIMITS
from ._text import truncate, sanitize_plain_text, sanitize_html
from .._types import ChannelMessage, ConfirmationRequest


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
    action_id_prefix: str = "confirm",
) -> Dict[str, Any]:
    """Build a Teams Adaptive Card for confirmation requests.

    Args:
        request: The confirmation request with options.
        action_id_prefix: Prefix for action IDs.

    Returns:
        Dict with Adaptive Card schema including ActionSet.
    """
    body: List[Dict[str, Any]] = []

    # Title
    if request.title:
        body.append({
            "type": "TextBlock",
            "text": request.title,
            "size": "Large",
            "weight": "Bolder",
            "wrap": True,
        })

    # Message
    if request.message:
        body.append({
            "type": "TextBlock",
            "text": request.message,
            "wrap": True,
        })

    # Action buttons
    actions = []
    for option in request.options:
        label = option.replace("_", " ").title()
        actions.append({
            "type": "Action.Submit",
            "title": label,
            "data": {"action_id": request.action_id, "option": option},
        })

    card: Dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }

    if actions:
        card["actions"] = actions

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
