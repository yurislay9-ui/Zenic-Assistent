"""
Slack Provider — Core SlackChannelProvider class.

Outbound: Web API (chat.postMessage) with Block Kit.
Inbound: Events API (HTTP) or Socket Mode (WebSocket).
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

from ..._formatter import (
    MessageFormatter,
    build_slack_blocks,
    build_slack_confirmation_blocks,
    format_slack_message,
    truncate,
)
from ..._protocol import ChannelProvider, InboundChannelProvider
from ..._types import (
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
from ._helpers import (
    _validate_url,
    _HAS_AIOHTTP,
    _HAS_URLLIB,
    _SLACK_API_BASE,
    _MAX_RETRIES,
    _RETRY_BASE_DELAY,
    _HTTP_TIMEOUT,
)

logger = logging.getLogger("zenic_agents.channels.slack")


class SlackChannelProvider:
    """Slack channel provider with Block Kit and Socket Mode support."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        app_token: Optional[str] = None,
        signing_secret: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> None:
        self._bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN", "")
        self._app_token = app_token or os.environ.get("SLACK_APP_TOKEN", "")
        self._signing_secret = signing_secret or os.environ.get("SLACK_SIGNING_SECRET", "")
        self._api_base = api_base or os.environ.get("SLACK_API_BASE", _SLACK_API_BASE)
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()
        self._message_handler: Optional[MessageHandler] = None
        self._confirmation_handler: Optional[ConfirmationHandler] = None
        self._session: Optional[Any] = None
        self._ws_session: Optional[Any] = None

    @property
    def name(self) -> str:
        return "slack"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        caps = {
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_RICH,
            ChannelCapability.SEND_CONFIRMATION,
            ChannelCapability.THREAD,
            ChannelCapability.REPLY,
        }
        if self._bot_token:
            caps.add(ChannelCapability.RECEIVE_MESSAGE)
            caps.add(ChannelCapability.RECEIVE_CONFIRMATION)
        return frozenset(caps)

    @property
    def is_available(self) -> bool:
        return bool(self._bot_token)

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send a message to Slack via chat.postMessage."""
        if not self._bot_token:
            return self._dry_run_send(message)

        payload = format_slack_message(message)
        payload["channel"] = message.recipient

        if message.fields:
            if "blocks" not in payload:
                payload["blocks"] = build_slack_blocks(message)
                payload["channel"] = message.recipient

        response = await self._post_api("chat.postMessage", payload)

        with self._lock:
            self._sent_count += 1 if response.success else 0
            self._failed_count += 0 if response.success else 1

        return response

    async def send_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send an interactive confirmation via Slack Block Kit buttons."""
        if not self._bot_token:
            return self._dry_run_confirmation(request)

        blocks = build_slack_confirmation_blocks(request)

        payload: Dict[str, Any] = {
            "channel": request.recipient,
            "blocks": blocks,
            "text": truncate(request.title or request.message, 150),
        }

        response = await self._post_api("chat.postMessage", payload)

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
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
            )

        self._started = True
        logger.info(
            "SlackChannelProvider: started (token=%s, socket_mode=%s)",
            bool(self._bot_token), bool(self._app_token),
        )

    async def stop(self) -> None:
        """Gracefully shut down."""
        if self._session and _HAS_AIOHTTP:
            await self._session.close()
            self._session = None
        self._started = False
        logger.info("SlackChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": "slack",
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "is_available": self.is_available,
                "has_bot_token": bool(self._bot_token),
                "has_app_token": bool(self._app_token),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        return self._rate_limit_info

    # ── InboundChannelProvider ──────────────────────────────────

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._message_handler = handler

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        self._confirmation_handler = handler

    @property
    def is_listening(self) -> bool:
        return self._started and bool(self._bot_token)

    def verify_signature(
        self, timestamp: str, body: str, signature: str,
    ) -> bool:
        """Verify Slack request signature (HMAC-SHA256)."""
        if not self._signing_secret:
            logger.warning("SlackChannelProvider: no signing secret configured")
            return False
        try:
            if abs(time.time() - float(timestamp)) > 300:
                return False
        except (ValueError, TypeError):
            return False

        sig_basestring = f"v0:{timestamp}:{body}"
        computed = "v0=" + hmac.new(
            self._signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare(computed, signature)

    # ── Internal: Slack API ────────────────────────────────────

    async def _post_api(
        self, endpoint: str, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """POST to a Slack Web API endpoint with retry."""
        url = f"{self._api_base}/{endpoint}"

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_api_aiohttp(url, payload)
                elif _HAS_URLLIB:
                    return await self._post_api_urllib(url, payload)
                else:
                    return ChannelResponse(
                        success=False, channel="slack",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "SlackChannelProvider: attempt %d/%d failed: %s",
                        attempt, _MAX_RETRIES, e,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    return ChannelResponse(
                        success=False, channel="slack",
                        status=DeliveryStatus.FAILED,
                        error=f"HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False, channel="slack",
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

            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                self._rate_limit_info = RateLimitInfo(
                    remaining=int(remaining),
                    reset_at=float(resp.headers.get("X-RateLimit-Reset", "0")),
                    limit=int(resp.headers.get("X-RateLimit-Limit", "-1")),
                )

            if resp.status == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                self._rate_limit_info = RateLimitInfo(remaining=0, reset_at=time.time() + retry_after)
                return ChannelResponse(
                    success=False, channel="slack",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"Rate limited. Retry after {retry_after}s",
                    timestamp=time.time(),
                )

            if body.get("ok"):
                message_ts = body.get("ts", "")
                return ChannelResponse(
                    success=True, channel="slack",
                    message_id=message_ts,
                    status=DeliveryStatus.SENT,
                    metadata={"ts": message_ts, "channel": body.get("channel", "")},
                    timestamp=time.time(),
                )
            else:
                return ChannelResponse(
                    success=False, channel="slack",
                    status=DeliveryStatus.FAILED,
                    error=f"Slack API error: {body.get('error', 'unknown_error')}",
                    timestamp=time.time(),
                )

    async def _post_api_urllib(
        self, url: str, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio
        validated_url = _validate_url(url)

        def _sync_post() -> ChannelResponse:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                validated_url, data=data,
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    if body.get("ok"):
                        return ChannelResponse(
                            success=True, channel="slack",
                            message_id=body.get("ts", ""),
                            status=DeliveryStatus.SENT,
                            metadata={"ts": body.get("ts", "")},
                            timestamp=time.time(),
                        )
                    else:
                        return ChannelResponse(
                            success=False, channel="slack",
                            status=DeliveryStatus.FAILED,
                            error=f"Slack API error: {body.get('error', 'unknown')}",
                            timestamp=time.time(),
                        )
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    retry_after = float(e.headers.get("Retry-After", "5"))
                    return ChannelResponse(
                        success=False, channel="slack",
                        status=DeliveryStatus.RATE_LIMITED,
                        error=f"Rate limited. Retry after {retry_after}s",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False, channel="slack",
                    status=DeliveryStatus.FAILED,
                    error=f"HTTP {e.code}: {e.read().decode()[:200]}",
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False, channel="slack",
                    status=DeliveryStatus.FAILED,
                    error=f"urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    # ── Internal: Dry Run ───────────────────────────────────────

    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        with self._lock:
            self._sent_count += 1
        logger.info(
            "[SLACK DRY-RUN] To: %s | Text: %s",
            message.recipient or "default",
            (message.text or "")[:200],
        )
        return ChannelResponse(
            success=True, channel="slack",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run"},
            timestamp=time.time(),
        )

    def _dry_run_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        with self._lock:
            self._confirmation_count += 1
        logger.info(
            "[SLACK DRY-RUN] Confirmation: %s | Options: %s",
            request.title, list(request.options),
        )
        return ChannelResponse(
            success=True, channel="slack",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "action_id": request.action_id},
            timestamp=time.time(),
        )
