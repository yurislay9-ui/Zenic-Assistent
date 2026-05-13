"""
A14 NotificationDispatcher — SINGLE RESPONSIBILITY: Send notifications across channels.

Deterministic notification dispatch: channel routing, recipient parsing, delivery tracking.
No AI. Pure string/structure manipulation.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import NotificationResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

VALID_CHANNELS = frozenset({
    "email", "sms", "push", "webhook",
    "slack", "teams", "log",
})

# Channel priority for fallback routing
CHANNEL_PRIORITY = {
    "email": 1,
    "sms": 2,
    "push": 3,
    "slack": 4,
    "teams": 5,
    "webhook": 6,
    "log": 7,
}

MAX_RECIPIENTS = 100
MAX_MESSAGE_LENGTH = 10000


class NotificationDispatcher(BaseAgent[NotificationResult]):
    """
    A14: Send notifications across channels (email, SMS, push).

    Single Responsibility: Notification dispatch ONLY.
    Method: Deterministic channel routing + recipient parsing.
    Fallback: NotificationResult with sent=False.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A14_NotificationDispatcher", **kwargs)

    def execute(self, input_data: Any) -> NotificationResult:
        """
        Dispatch notification: route to channel, parse recipients.

        Input (BusinessData.data dict):
            - channel / type: "email"|"sms"|"push"|"webhook"|"slack"|"teams"|"log"
            - recipients / to: str or list of str
            - message / body: str (notification content)
            - subject: str (optional, for email)

        Output: NotificationResult with sent, channel, status.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        channel = str(data.get("channel", data.get("type", "log"))).lower()
        recipients = data.get("recipients", data.get("to", []))
        message = str(data.get("message", data.get("body", "")))

        # ── Validate channel ──
        if channel not in VALID_CHANNELS:
            channel = "log"  # Safe default

        # ── Parse recipients ──
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        elif not isinstance(recipients, list):
            recipients = []

        # Cap recipients
        recipients = recipients[:MAX_RECIPIENTS]

        # ── Truncate message ──
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[:MAX_MESSAGE_LENGTH]

        # ── Dispatch logic ──
        # In a real system, this would call external services.
        # Here we just validate and mark as dispatched.
        sent = len(recipients) > 0 or channel == "log"
        status = "dispatched" if sent else "no_recipients"

        return NotificationResult(
            sent=sent,
            channel=channel,
            status=status,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> NotificationResult:
        """Safe fallback: notification not sent."""
        return NotificationResult(
            sent=False, channel="", status="fallback_not_sent",
            source="fallback",
        )
