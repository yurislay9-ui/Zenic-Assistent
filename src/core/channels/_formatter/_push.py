"""ZENIC-AGENTS - Channel Formatter: Push"""

from __future__ import annotations

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
    from ._types import ChannelPriority
    priority_map = {
        ChannelPriority.LOW: "normal",
        ChannelPriority.NORMAL: "normal",
        ChannelPriority.HIGH: "high",
        ChannelPriority.URGENT: "high",
        ChannelPriority.EMERGENCY: "high",
    }
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
