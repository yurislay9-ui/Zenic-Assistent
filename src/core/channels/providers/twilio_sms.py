"""
ZENIC-AGENTS — Twilio SMS Channel Provider

Outbound: Twilio REST API (SMS/MMS)
Inbound:  Twilio webhook callbacks with signature verification

Supports:
  - SMS (160 chars/segment, auto-splitting)
  - MMS (media attachments via URL)
  - Webhook signature verification (Twilio HMAC-SHA1)
  - From/To number management
  - Rate limit awareness (Twilio API limits)
  - Retry with exponential backoff
  - Dry-run mode when no credentials configured

Configuration (env vars or constructor):
  - TWILIO_ACCOUNT_SID:  Account SID (ACxxxx)
  - TWILIO_AUTH_TOKEN:   Auth token
  - TWILIO_PHONE_NUMBER: From phone number (+1xxx)

Design invariants:
  1. Never raises — always returns ChannelResponse.
  2. HMAC-SHA1 verification for inbound webhooks (Twilio standard).
  3. Uses aiohttp when available, falls back to urllib.
  4. SMS text auto-truncated to 160 chars per segment.
  5. Dry-run mode when unconfigured.
  6. Thread-safe stats.
  7. No heavy SDK dependencies — pure HTTP.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import threading
import time
import urllib.parse
from typing import Any, Dict, FrozenSet, List, Optional
from urllib.parse import urlparse

from .._formatter import (
    MessageFormatter,
    format_sms_text,
    split_message,
    truncate,
    sanitize_plain_text,
)
from .._protocol import ChannelProvider, InboundChannelProvider
from .._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationHandler,
    ConfirmationRequest,
    ConfirmationResult,
    DeliveryStatus,
    MessageHandler,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.twilio_sms")


def _validate_url(url: str, allowed_schemes: tuple = ("http", "https")) -> str:
    """Validate URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Use: {allowed_schemes}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            raise ValueError(f"Access to internal IPs is not allowed: {parsed.hostname}")
    except ValueError:
        pass  # hostname is not an IP, that's OK
    return url


# ── Optional Dependencies ─────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


# ── Constants ─────────────────────────────────────────────────

_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5
_HTTP_TIMEOUT = 30
_SMS_CHAR_LIMIT = 160
_MMS_CHAR_LIMIT = 1600


class TwilioSMSChannelProvider:
    """Twilio SMS/MMS channel provider.

    Supports:
      - Outbound: SMS and MMS via Twilio REST API
      - Inbound: Webhook callbacks with signature verification
      - Auto-splitting long messages into segments
      - Dry-run mode when unconfigured

    Complexity: 🟢 Low — straightforward REST API with form-encoded POSTs.
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
        self._api_base = api_base or os.environ.get("TWILIO_API_BASE", _TWILIO_API_BASE)
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()
        self._message_handler: Optional[MessageHandler] = None
        self._confirmation_handler: Optional[ConfirmationHandler] = None
        self._session: Optional[Any] = None

    # ── ChannelProvider Protocol ────────────────────────────────

    @property
    def name(self) -> str:
        return "sms"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        return frozenset({
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_SMS,
            ChannelCapability.SEND_MMS,
            ChannelCapability.SEND_CONFIRMATION,
            ChannelCapability.RECEIVE_MESSAGE,
            ChannelCapability.REPLY,
        })

    @property
    def is_available(self) -> bool:
        """Available if Account SID, Auth Token, and phone number are configured."""
        return bool(self._account_sid and self._auth_token and self._phone_number)

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send an SMS/MMS via Twilio REST API.

        - If message.image_url is set, sends as MMS.
        - Otherwise, sends as SMS with auto-splitting for long texts.
        - Confirmation requests are formatted as SMS with reply instructions.

        Args:
            message: Universal message envelope.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self.is_available:
            return self._dry_run_send(message)

        # Determine if MMS
        is_mms = bool(message.image_url or message.file_url)

        # Format text for SMS
        text = format_sms_text(message)
        if not text:
            text = message.text or ""

        text = sanitize_plain_text(text)

        # Split long messages
        char_limit = _MMS_CHAR_LIMIT if is_mms else _SMS_CHAR_LIMIT
        segments = split_message(text, char_limit) if len(text) > char_limit else [text]

        # Send each segment
        last_response: Optional[ChannelResponse] = None
        total_segments = len(segments)

        for i, segment in enumerate(segments):
            payload: Dict[str, str] = {
                "From": self._phone_number,
                "To": message.recipient,
                "Body": segment,
            }

            # Add media for MMS (first segment only)
            if is_mms and i == 0:
                media_url = message.image_url or message.file_url or ""
                if media_url:
                    payload["MediaUrl"] = media_url

            response = await self._post_api(payload)

            with self._lock:
                self._sent_count += 1 if response.success else 0
                self._failed_count += 0 if response.success else 1

            last_response = response

            # If one segment fails, stop sending
            if not response.success:
                return response

        # Add segment metadata
        if last_response and total_segments > 1:
            return ChannelResponse(
                success=last_response.success,
                channel="sms",
                message_id=last_response.message_id,
                status=last_response.status,
                error=last_response.error,
                metadata={**last_response.metadata, "segments": total_segments},
                timestamp=last_response.timestamp,
            )

        return last_response or ChannelResponse(
            success=False, channel="sms",
            status=DeliveryStatus.FAILED,
            error="No message content to send",
            timestamp=time.time(),
        )

    async def send_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send a confirmation request via SMS.

        Since SMS doesn't support interactive buttons, the confirmation
        is formatted as a plain text message with reply instructions.

        Format:
          "⚠️ Confirmation: [title]
           [message]
           Reply YES/NO/MORE"

        Args:
            request: Confirmation request.

        Returns:
            ChannelResponse with delivery result.
        """
        # Build SMS-friendly confirmation text
        parts: List[str] = []

        if request.title:
            parts.append(f"⚠️ {request.title}")

        if request.message:
            parts.append(request.message)

        # Add reply instructions
        option_labels = {
            "yes": "YES",
            "no": "NO",
            "more_info": "MORE",
        }
        options_text = "/".join(
            option_labels.get(o, o.upper()) for o in request.options
        )
        parts.append(f"Reply {options_text}")

        text = "\n".join(parts)

        # Send as regular SMS
        msg = ChannelMessage(
            text=text,
            recipient=request.recipient,
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

        if _HAS_AIOHTTP and not self._session:
            # Twilio uses Basic Auth
            credentials = base64.b64encode(
                f"{self._account_sid}:{self._auth_token}".encode("utf-8")
            ).decode("utf-8")

            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT),
                headers={
                    "Authorization": f"Basic {credentials}",
                },
            )

        self._started = True
        logger.info(
            "TwilioSMSChannelProvider: started (configured=%s)", self.is_available,
        )

    async def stop(self) -> None:
        """Gracefully shut down."""
        if self._session and _HAS_AIOHTTP:
            await self._session.close()
            self._session = None

        self._started = False
        logger.info("TwilioSMSChannelProvider: stopped")

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
    def rate_limit_info(self) -> RateLimitInfo:
        """Current rate limit status."""
        return self._rate_limit_info

    # ── InboundChannelProvider Protocol ─────────────────────────

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register a handler for incoming SMS messages."""
        self._message_handler = handler
        logger.debug("TwilioSMSChannelProvider: message handler registered")

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        """Register a handler for SMS reply confirmations."""
        self._confirmation_handler = handler
        logger.debug("TwilioSMSChannelProvider: confirmation handler registered")

    @property
    def is_listening(self) -> bool:
        """Whether the provider is ready for inbound webhooks."""
        return self._started and self.is_available

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
        if not self._auth_token:
            logger.warning("TwilioSMSChannelProvider: no auth token configured")
            return False

        # Build the signature base string
        sig_base = url
        for key in sorted(params.keys()):
            sig_base += key + params[key]

        # Compute HMAC-SHA1
        computed = base64.b64encode(
            hmac.new(
                self._auth_token.encode("utf-8"),
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

    # ── Internal: API ───────────────────────────────────────────

    async def _post_api(self, payload: Dict[str, str]) -> ChannelResponse:
        """POST to Twilio Messages API.

        Uses form-encoded data (Twilio's expected format).
        """
        url = _validate_url(f"{self._api_base}/Accounts/{self._account_sid}/Messages.json")

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_api_aiohttp(url, payload)
                elif _HAS_URLLIB:
                    return await self._post_api_urllib(url, payload)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="sms",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="sms",
                        status=DeliveryStatus.FAILED,
                        error=f"HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False, channel="sms",
            status=DeliveryStatus.FAILED,
            error="Unexpected retry loop exit",
            timestamp=time.time(),
        )

    async def _post_api_aiohttp(
        self, url: str, payload: Dict[str, str],
    ) -> ChannelResponse:
        """Send via aiohttp (form-encoded)."""
        assert self._session is not None

        async with self._session.post(url, data=payload) as resp:
            body = await resp.json()

            if resp.status == 201 or resp.status == 200:
                msg_sid = body.get("sid", "")
                return ChannelResponse(
                    success=True,
                    channel="sms",
                    message_id=msg_sid,
                    status=DeliveryStatus.SENT,
                    metadata={"twilio_sid": msg_sid, "status": body.get("status", "")},
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                return ChannelResponse(
                    success=False,
                    channel="sms",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"Rate limited: {body}",
                    timestamp=time.time(),
                )
            else:
                error_msg = body.get("message", str(body)[:200])
                return ChannelResponse(
                    success=False,
                    channel="sms",
                    status=DeliveryStatus.FAILED,
                    error=f"Twilio API error ({resp.status}): {error_msg}",
                    timestamp=time.time(),
                )

    async def _post_api_urllib(
        self, url: str, payload: Dict[str, str],
    ) -> ChannelResponse:
        """Send via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio

        def _sync_post() -> ChannelResponse:
            credentials = base64.b64encode(
                f"{self._account_sid}:{self._auth_token}".encode("utf-8")
            ).decode("utf-8")

            encoded = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=encoded,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    msg_sid = body.get("sid", "")
                    return ChannelResponse(
                        success=True,
                        channel="sms",
                        message_id=msg_sid,
                        status=DeliveryStatus.SENT,
                        metadata={"twilio_sid": msg_sid},
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:300]
                if e.code == 429:
                    return ChannelResponse(
                        success=False,
                        channel="sms",
                        status=DeliveryStatus.RATE_LIMITED,
                        error="Rate limited",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False,
                    channel="sms",
                    status=DeliveryStatus.FAILED,
                    error=f"HTTP {e.code}: {body}",
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False,
                    channel="sms",
                    status=DeliveryStatus.FAILED,
                    error=f"urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    # ── Internal: Dry Run ───────────────────────────────────────

    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        """Log message without sending."""
        with self._lock:
            self._sent_count += 1

        text = format_sms_text(message)
        text_preview = text[:80]
        logger.info(
            "[SMS DRY-RUN] To: %s | Text: %s%s",
            message.recipient or "default",
            text_preview,
            "..." if len(text) > 80 else "",
        )

        return ChannelResponse(
            success=True,
            channel="sms",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "char_count": len(text)},
            timestamp=time.time(),
        )


__all__ = ["TwilioSMSChannelProvider"]
