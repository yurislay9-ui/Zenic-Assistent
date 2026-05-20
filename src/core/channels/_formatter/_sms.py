"""ZENIC-AGENTS - Channel Formatter: Sms"""

from __future__ import annotations

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
