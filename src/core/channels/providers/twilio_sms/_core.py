"""twilio_sms — Core implementation (class definition + public API)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any, Dict, FrozenSet, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _post_api, _post_api_aiohttp, _post_api_urllib, _dry_run_send
from ._transport import TwilioSMSTransportMixin


class TwilioSMSChannelProvider(TwilioSMSTransportMixin):
    """Twilio SMS/MMS channel provider.

    Supports:
      - Outbound: SMS and MMS via Twilio REST API
      - Inbound: Webhook callbacks with signature verification
      - Auto-splitting long messages into segments
      - Dry-run mode when unconfigured
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        phone_number: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> None:
        self._account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID", "")
        self._auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN", "")
        self._phone_number = phone_number or os.environ.get("TWILIO_PHONE_NUMBER", "")
        self._api_base = api_base or os.environ.get("TWILIO_API_BASE", _TWILIO_API_BASE)  # noqa: F821
        import threading
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()  # noqa: F821
        self._message_handler: Optional[MessageHandler] = None  # noqa: F821
        self._confirmation_handler: Optional[ConfirmationHandler] = None  # noqa: F821
        self._session: Optional[Any] = None

    # ── ChannelProvider Protocol ────────────────────────────────

    @property
    def name(self) -> str:
        return "sms"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:  # noqa: F821
        return frozenset({
            ChannelCapability.SEND_TEXT,  # noqa: F821
            ChannelCapability.SEND_SMS,  # noqa: F821
            ChannelCapability.SEND_MMS,  # noqa: F821
            ChannelCapability.SEND_CONFIRMATION,  # noqa: F821
            ChannelCapability.RECEIVE_MESSAGE,  # noqa: F821
            ChannelCapability.REPLY,  # noqa: F821
        })

    @property
    def is_available(self) -> bool:
        """Available if Account SID, Auth Token, and phone number are configured."""
        return bool(self._account_sid and self._auth_token and self._phone_number)

    async def send(self, message: ChannelMessage) -> ChannelResponse:  # noqa: F821
        """Send an SMS/MMS via Twilio REST API."""
        if not self.is_available:
            return self._dry_run_send(message)

        is_mms = bool(message.image_url or message.file_url)
        text = format_sms_text(message)  # noqa: F821
        if not text:
            text = message.text or ""
        text = sanitize_plain_text(text)  # noqa: F821

        char_limit = _MMS_CHAR_LIMIT if is_mms else _SMS_CHAR_LIMIT  # noqa: F821
        segments = split_message(text, char_limit) if len(text) > char_limit else [text]  # noqa: F821

        last_response: Optional[ChannelResponse] = None
        total_segments = len(segments)

        for i, segment in enumerate(segments):
            payload: Dict[str, str] = {
                "From": self._phone_number,
                "To": message.recipient,
                "Body": segment,
            }
            if is_mms and i == 0:
                media_url = message.image_url or message.file_url or ""
                if media_url:
                    payload["MediaUrl"] = media_url

            response = await self._post_api(payload)

            with self._lock:
                self._sent_count += 1 if response.success else 0
                self._failed_count += 0 if response.success else 1

            last_response = response
            if not response.success:
                return response

        if last_response and total_segments > 1:
            return ChannelResponse(
                success=last_response.success, channel="sms",
                message_id=last_response.message_id,
                status=last_response.status, error=last_response.error,
                metadata={**last_response.metadata, "segments": total_segments},
                timestamp=last_response.timestamp,
            )

        return last_response or ChannelResponse(
            success=False, channel="sms",
            status=DeliveryStatus.FAILED,  # noqa: F821
            error="No message content to send", timestamp=time.time(),
        )

    async def send_confirmation(
        self, request: ConfirmationRequest,  # noqa: F821
    ) -> ChannelResponse:
        """Send a confirmation request via SMS."""
        parts: List[str] = []
        if request.title:
            parts.append(f"⚠️ {request.title}")
        if request.message:
            parts.append(request.message)
        option_labels = {"yes": "YES", "no": "NO", "more_info": "MORE"}
        options_text = "/".join(option_labels.get(o, o.upper()) for o in request.options)
        parts.append(f"Reply {options_text}")
        text = "\n".join(parts)

        msg = ChannelMessage(  # noqa: F821
            text=text, recipient=request.recipient,
            metadata={"action_id": request.action_id, "type": "confirmation"},
        )
        response = await self.send(msg)
        with self._lock:
            self._confirmation_count += 1
        return response

    async def start(self) -> None:
        """Initialize the provider."""
        if self._started:
            return
        if _HAS_AIOHTTP and not self._session:  # noqa: F821
            credentials = base64.b64encode(
                f"{self._account_sid}:{self._auth_token}".encode("utf-8")
            ).decode("utf-8")
            self._session = aiohttp.ClientSession(  # noqa: F821
                timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT),  # noqa: F821
                headers={"Authorization": f"Basic {credentials}"},
            )
        self._started = True
        __import__("logging").getLogger("zenic_agents.channels.twilio_sms").info(
            "TwilioSMSChannelProvider: started (configured=%s)", self.is_available,
        )

    async def stop(self) -> None:
        """Gracefully shut down."""
        if self._session and _HAS_AIOHTTP:  # noqa: F821
            await self._session.close()
            self._session = None
        self._started = False
        __import__("logging").getLogger("zenic_agents.channels.twilio_sms").info("TwilioSMSChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics."""
        with self._lock:
            return {
                "name": "sms",
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "is_available": self.is_available,
                "has_credentials": bool(self._account_sid and self._auth_token),
                "has_phone_number": bool(self._phone_number),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> "RateLimitInfo":  # noqa: F821
        """Current rate limit status."""
        return self._rate_limit_info

    # ── InboundChannelProvider Protocol ─────────────────────────

    def set_message_handler(self, handler: "MessageHandler") -> None:  # noqa: F821
        """Register a handler for incoming SMS messages."""
        self._message_handler = handler

    def set_confirmation_handler(self, handler: "ConfirmationHandler") -> None:  # noqa: F821
        """Register a handler for SMS reply confirmations."""
        self._confirmation_handler = handler

    @property
    def is_listening(self) -> bool:
        """Whether the provider is ready for inbound webhooks."""
        return self._started and self.is_available

    # ── Webhook Signature Verification ──────────────────────────

    def verify_signature(self, url: str, params: Dict[str, str], signature: str) -> bool:
        """Verify Twilio webhook signature (HMAC-SHA1)."""
        if not self._auth_token:
            return False
        sig_base = url
        for key in sorted(params.keys()):
            sig_base += key + params[key]
        computed = base64.b64encode(
            hmac.new(
                self._auth_token.encode("utf-8"),
                sig_base.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return hmac.compare(computed, signature)

    def parse_inbound_message(self, params: Dict[str, str]) -> Optional[ChannelMessage]:  # noqa: F821
        """Parse a Twilio webhook POST into a ChannelMessage."""
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
        media_urls: List[str] = []
        for i in range(num_media):
            url = params.get(f"MediaUrl{i}", "")
            if url:
                media_urls.append(url)
        if media_urls:
            metadata["media_urls"] = media_urls

        return ChannelMessage(
            text=body, recipient=from_number, metadata=metadata,
        )


__all__ = ["TwilioSMSChannelProvider"]
