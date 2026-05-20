"""
ZENIC-AGENTS — WhatsApp Business Channel Provider — Webhook Module

Inbound:  Webhook callbacks with HMAC-SHA256 signature verification
Supports:
  - Webhook subscription verification (Meta GET handshake)
  - HMAC-SHA256 payload signature verification
  - Inbound message parsing (text, interactive replies)
  - Message and confirmation handler registration
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional

from ..._protocol import InboundChannelProvider
from ..._types import (
    ChannelMessage,
    ConfirmationHandler,
    MessageHandler,
)

logger = logging.getLogger("zenic_agents.channels.whatsapp")


class WhatsAppWebhookMixin:
    """Mixin providing WhatsApp webhook and inbound message functionality.

    Intended to be mixed into WhatsAppChannelProviderBase to form
    the complete WhatsAppChannelProvider.
    """

    # ── InboundChannelProvider Protocol ─────────────────────────

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register a handler for incoming WhatsApp messages."""
        self._message_handler: Optional[MessageHandler] = handler  # type: ignore[attr-defined]
        logger.debug("WhatsAppChannelProvider: message handler registered")

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        """Register a handler for button callback responses."""
        self._confirmation_handler: Optional[ConfirmationHandler] = handler  # type: ignore[attr-defined]
        logger.debug("WhatsAppChannelProvider: confirmation handler registered")

    @property
    def is_listening(self) -> bool:
        """Whether the provider is actively listening."""
        return self._started and self.is_available  # type: ignore[attr-defined]

    # ── Webhook Verification ────────────────────────────────────

    def verify_webhook(self, mode: str, token: str) -> bool:
        """Verify WhatsApp webhook subscription request.

        Called during GET /webhook verification by Meta.

        Args:
            mode: hub.mode (must be "subscribe")
            token: hub.verify_token (must match configured verify_token)

        Returns:
            True if verification succeeds, False otherwise.
        """
        if not self._verify_token:  # type: ignore[attr-defined]
            logger.warning("WhatsAppChannelProvider: no verify token configured")
            return False

        return mode == "subscribe" and token == self._verify_token  # type: ignore[attr-defined]

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify WhatsApp webhook payload signature (HMAC-SHA256).

        Args:
            payload: Raw request body bytes.
            signature: X-Hub-Signature-256 header value.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not self._app_secret:  # type: ignore[attr-defined]
            logger.warning("WhatsAppChannelProvider: no app secret configured")
            return False

        if not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            self._app_secret.encode("utf-8"),  # type: ignore[attr-defined]
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare(expected, signature[7:])

    def parse_inbound_message(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """Parse a WhatsApp webhook payload into a ChannelMessage.

        Args:
            payload: Parsed JSON body from webhook POST.

        Returns:
            ChannelMessage if valid, None if not a message event.
        """
        try:
            entry = payload.get("entry", [{}])[0]
            change = entry.get("changes", [{}])[0]
            value = change.get("value", {})

            # Skip status updates
            if "statuses" in value:
                return None

            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            msg_type = msg.get("type", "text")
            phone_number = msg.get("from", "")
            msg_id = msg.get("id", "")

            text = ""
            if msg_type == "text":
                text = msg.get("text", {}).get("body", "")
            elif msg_type == "interactive":
                interactive = msg.get("interactive", {})
                interactive_type = interactive.get("type", "")
                if interactive_type == "button_reply":
                    text = interactive.get("button_reply", {}).get("title", "")
                elif interactive_type == "list_reply":
                    text = interactive.get("list_reply", {}).get("title", "")

            return ChannelMessage(
                text=text,
                recipient=phone_number,
                reply_to=msg_id,
                metadata={
                    "whatsapp_message_id": msg_id,
                    "whatsapp_type": msg_type,
                    "from_phone": phone_number,
                },
            )
        except (IndexError, KeyError, TypeError) as e:
            logger.warning("WhatsAppChannelProvider: failed to parse inbound: %s", e)
            return None


__all__ = ["WhatsAppWebhookMixin"]
