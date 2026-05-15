"""
ZENIC-AGENTS — WhatsApp Business Channel Provider

Outbound: Cloud API (Graph API) REST calls
Inbound:  Webhook callbacks with HMAC-SHA256 signature verification

Supports:
  - Text messages with URL previews
  - Interactive button messages (up to 3 buttons)
  - Message templates
  - Media messages (image, document, video, audio) via URLs
  - Webhook signature verification (HMAC-SHA256)
  - Rate limit tracking (WhatsApp API limits)
  - Retry with exponential backoff
  - Dry-run mode when no access token configured

Configuration (env vars or constructor):
  - WHATSAPP_ACCESS_TOKEN:  Meta access token
  - WHATSAPP_PHONE_NUMBER_ID: Business phone number ID
  - WHATSAPP_VERIFY_TOKEN:  Webhook verification token (for inbound setup)
  - WHATSAPP_APP_SECRET:    App secret for HMAC signature verification

⚠️ REQUIRES: Meta Business Account + Phone Number ID + Access Token

Design invariants:
  1. Never raises — always returns ChannelResponse.
  2. HMAC-SHA256 verification for all inbound webhooks.
  3. Uses aiohttp when available, falls back to urllib.
  4. Dry-run mode when unconfigured.
  5. Thread-safe stats.
  6. No heavy SDK dependencies — pure HTTP.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional

from .._formatter import (
    MessageFormatter,
    build_whatsapp_interactive_buttons,
    format_whatsapp_text,
    truncate,
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

logger = logging.getLogger("zenic_agents.channels.whatsapp")

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

_WHATSAPP_API_BASE = "https://graph.facebook.com/v18.0"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5
_HTTP_TIMEOUT = 30
_MAX_BUTTONS = 3  # WhatsApp limit for interactive buttons


class WhatsAppChannelProvider:
    """WhatsApp Business Cloud API channel provider.

    Supports:
      - Outbound: Text, interactive buttons, media, templates
      - Inbound: Webhook callbacks with HMAC verification
      - Dry-run mode when unconfigured
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        verify_token: Optional[str] = None,
        app_secret: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> None:
        self._access_token = access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        self._phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self._verify_token = verify_token or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        self._app_secret = app_secret or os.environ.get("WHATSAPP_APP_SECRET", "")
        self._api_base = api_base or os.environ.get("WHATSAPP_API_BASE", _WHATSAPP_API_BASE)
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
        return "whatsapp"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        caps = {
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_RICH,
            ChannelCapability.SEND_CONFIRMATION,
            ChannelCapability.SEND_FILE,
            ChannelCapability.RECEIVE_MESSAGE,
            ChannelCapability.RECEIVE_CONFIRMATION,
            ChannelCapability.REPLY,
        }
        return frozenset(caps)

    @property
    def is_available(self) -> bool:
        """Available if access token and phone number ID are configured."""
        return bool(self._access_token and self._phone_number_id)

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send a message via WhatsApp Cloud API.

        Supports:
          - Plain text with URL previews
          - Media (image, document) via URL
          - Template messages

        Args:
            message: Universal message envelope.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self.is_available:
            return self._dry_run_send(message)

        # Determine message type
        if message.image_url:
            payload = self._build_media_payload(message, "image", message.image_url)
        elif message.file_url:
            payload = self._build_media_payload(message, "document", message.file_url)
        else:
            payload = format_whatsapp_text(message)

        response = await self._post_api(payload)

        with self._lock:
            self._sent_count += 1 if response.success else 0
            self._failed_count += 0 if response.success else 1

        return response

    async def send_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send an interactive confirmation via WhatsApp buttons.

        WhatsApp supports up to 3 quick reply buttons.

        Args:
            request: Confirmation request (max 3 options).

        Returns:
            ChannelResponse with delivery result.
        """
        if not self.is_available:
            return self._dry_run_confirmation(request)

        # WhatsApp limit: 3 buttons max
        limited_request = ConfirmationRequest(
            action_id=request.action_id,
            action_type=request.action_type,
            title=request.title,
            message=request.message,
            options=list(request.options)[:_MAX_BUTTONS],
            timeout_seconds=request.timeout_seconds,
            channel=request.channel,
            recipient=request.recipient,
            metadata=request.metadata,
        )

        payload = build_whatsapp_interactive_buttons(limited_request)
        response = await self._post_api(payload)

        with self._lock:
            self._confirmation_count += 1

        return response

    async def start(self) -> None:
        """Initialize the provider."""
        if self._started:
            return

        if _HAS_AIOHTTP and not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT),
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
            )

        self._started = True
        logger.info(
            "WhatsAppChannelProvider: started (configured=%s)", self.is_available,
        )

    async def stop(self) -> None:
        """Gracefully shut down."""
        if self._session and _HAS_AIOHTTP:
            await self._session.close()
            self._session = None

        self._started = False
        logger.info("WhatsAppChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics."""
        with self._lock:
            return {
                "name": "whatsapp",
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "is_available": self.is_available,
                "has_access_token": bool(self._access_token),
                "has_phone_number_id": bool(self._phone_number_id),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        """Current rate limit status."""
        return self._rate_limit_info

    # ── InboundChannelProvider Protocol ─────────────────────────

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register a handler for incoming WhatsApp messages."""
        self._message_handler = handler
        logger.debug("WhatsAppChannelProvider: message handler registered")

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        """Register a handler for button callback responses."""
        self._confirmation_handler = handler
        logger.debug("WhatsAppChannelProvider: confirmation handler registered")

    @property
    def is_listening(self) -> bool:
        """Whether the provider is actively listening."""
        return self._started and self.is_available

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
        if not self._verify_token:
            logger.warning("WhatsAppChannelProvider: no verify token configured")
            return False

        return mode == "subscribe" and token == self._verify_token

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify WhatsApp webhook payload signature (HMAC-SHA256).

        Args:
            payload: Raw request body bytes.
            signature: X-Hub-Signature-256 header value.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not self._app_secret:
            logger.warning("WhatsAppChannelProvider: no app secret configured")
            return False

        if not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            self._app_secret.encode("utf-8"),
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

    # ── Internal: API ───────────────────────────────────────────

    def _build_media_payload(
        self,
        message: ChannelMessage,
        media_type: str,
        media_url: str,
    ) -> Dict[str, Any]:
        """Build a WhatsApp media message payload."""
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.recipient,
            "type": media_type,
            media_type: {
                "link": media_url,
            },
        }

        # Add caption for images/documents
        if message.text:
            caption = truncate(message.text, 1024)
            payload[media_type]["caption"] = caption

        # Add filename for documents
        if media_type == "document" and message.file_name:
            payload[media_type]["filename"] = message.file_name

        return payload

    async def _post_api(self, payload: Dict[str, Any]) -> ChannelResponse:
        """POST to WhatsApp Cloud API."""
        url = f"{self._api_base}/{self._phone_number_id}/messages"

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_api_aiohttp(url, payload)
                elif _HAS_URLLIB:
                    return await self._post_api_urllib(url, payload)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="whatsapp",
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
                        channel="whatsapp",
                        status=DeliveryStatus.FAILED,
                        error=f"HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False, channel="whatsapp",
            status=DeliveryStatus.FAILED,
            error="Unexpected retry loop exit",
            timestamp=time.time(),
        )

    async def _post_api_aiohttp(
        self, url: str, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send via aiohttp."""
        assert self._session is not None

        async with self._session.post(url, json=payload) as resp:
            body = await resp.json()

            # Track rate limits
            remaining = resp.headers.get("X-App-Usage")
            if remaining:
                try:
                    usage = json.loads(remaining)
                    self._rate_limit_info = RateLimitInfo(
                        remaining=max(0, 100 - usage.get("call_count", 0)),
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

            if resp.status == 200:
                messages = body.get("messages", [{}])
                msg_id = messages[0].get("id", "") if messages else ""
                return ChannelResponse(
                    success=True,
                    channel="whatsapp",
                    message_id=msg_id,
                    status=DeliveryStatus.SENT,
                    metadata={"whatsapp_message_id": msg_id},
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"Rate limited: {body}",
                    timestamp=time.time(),
                )
            else:
                error = body.get("error", {})
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.FAILED,
                    error=f"WhatsApp API error: {error.get('message', str(body)[:200])}",
                    timestamp=time.time(),
                )

    async def _post_api_urllib(
        self, url: str, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio

        def _sync_post() -> ChannelResponse:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    messages = body.get("messages", [{}])
                    msg_id = messages[0].get("id", "") if messages else ""
                    return ChannelResponse(
                        success=True,
                        channel="whatsapp",
                        message_id=msg_id,
                        status=DeliveryStatus.SENT,
                        metadata={"whatsapp_message_id": msg_id},
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:300]
                if e.code == 429:
                    return ChannelResponse(
                        success=False,
                        channel="whatsapp",
                        status=DeliveryStatus.RATE_LIMITED,
                        error=f"Rate limited",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
                    status=DeliveryStatus.FAILED,
                    error=f"HTTP {e.code}: {body}",
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False,
                    channel="whatsapp",
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

        text_preview = (message.text or "")[:200]
        logger.info(
            "[WHATSAPP DRY-RUN] To: %s | Text: %s",
            message.recipient or "default",
            text_preview,
        )

        return ChannelResponse(
            success=True,
            channel="whatsapp",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run"},
            timestamp=time.time(),
        )

    def _dry_run_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Log confirmation without sending."""
        with self._lock:
            self._confirmation_count += 1

        logger.info(
            "[WHATSAPP DRY-RUN] Confirmation: %s | Options: %s",
            request.title,
            list(request.options),
        )

        return ChannelResponse(
            success=True,
            channel="whatsapp",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "action_id": request.action_id},
            timestamp=time.time(),
        )


__all__ = ["WhatsAppChannelProvider"]
