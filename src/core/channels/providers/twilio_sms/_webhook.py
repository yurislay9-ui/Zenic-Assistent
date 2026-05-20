"""
ZENIC-AGENTS — Twilio SMS Channel Provider — Webhook Module

Inbound:  Twilio webhook callbacks with signature verification
Supports:
  - Webhook signature verification (Twilio HMAC-SHA1)
  - Inbound message parsing
  - Message and confirmation handler registration
"""

from __future__ import annotations

import base64
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

logger = logging.getLogger("zenic_agents.channels.twilio_sms")


class TwilioWebhookMixin:
    """Mixin providing Twilio webhook and inbound message functionality.

    Intended to be mixed into TwilioSMSChannelProviderBase to form
    the complete TwilioSMSChannelProvider.
    """

    # ── InboundChannelProvider Protocol ─────────────────────────

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register a handler for incoming SMS messages."""
        self._message_handler: Optional[MessageHandler] = handler  # type: ignore[attr-defined]
        logger.debug("TwilioSMSChannelProvider: message handler registered")

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        """Register a handler for SMS reply confirmations."""
        self._confirmation_handler: Optional[ConfirmationHandler] = handler  # type: ignore[attr-defined]
        logger.debug("TwilioSMSChannelProvider: confirmation handler registered")

    @property
    def is_listening(self) -> bool:
        """Whether the provider is ready for inbound webhooks."""
        return self._started and self.is_available  # type: ignore[attr-defined]

    # ── Webhook Signature Verification ──────────────────────────

    def verify_signature(
        self,
        url: str,
        params: Dict[str, str],
        signature: str,
    ) -> bool:
        """Verify Twilio webhook signature (HMAC-SHA1).

        Twilio signs requests by:
          1. Concatenating URL + sorted POST params
          2. Computing HMAC-SHA1 with Auth Token as key

        Args:
            url: The full URL of the webhook endpoint.
            params: POST parameters (form-encoded).
            signature: X-Twilio-Signature header value.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not self._auth_token:  # type: ignore[attr-defined]
            logger.warning("TwilioSMSChannelProvider: no auth token configured")
            return False

        # Build the signature base string
        sig_base = url
        for key in sorted(params.keys()):
            sig_base += key + params[key]

        # Compute HMAC-SHA1
        computed = base64.b64encode(
            hmac.new(
                self._auth_token.encode("utf-8"),  # type: ignore[attr-defined]
                sig_base.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")

        return hmac.compare(computed, signature)

    def parse_inbound_message(
        self,
        params: Dict[str, str],
    ) -> Optional[ChannelMessage]:
        """Parse a Twilio webhook POST into a ChannelMessage.

        Args:
            params: Form-encoded POST parameters from Twilio.

        Returns:
            ChannelMessage if valid, None otherwise.
        """
        body = params.get("Body", "")
        from_number = params.get("From", "")
        to_number = params.get("To", "")
        msg_sid = params.get("MessageSid", "")
        num_media = int(params.get("NumMedia", "0"))

        if not body and num_media == 0:
            return None

        metadata: Dict[str, Any] = {
            "twilio_message_sid": msg_sid,
            "twilio_account_sid": params.get("AccountSid", ""),
            "from_number": from_number,
            "to_number": to_number,
        }

        # Add media URLs if MMS
        media_urls: List[str] = []
        for i in range(num_media):
            url = params.get(f"MediaUrl{i}", "")
            if url:
                media_urls.append(url)

        if media_urls:
            metadata["media_urls"] = media_urls

        return ChannelMessage(
            text=body,
            recipient=from_number,  # Reply to the sender
            metadata=metadata,
        )


__all__ = ["TwilioWebhookMixin"]
