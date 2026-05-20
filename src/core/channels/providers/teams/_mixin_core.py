"""
Teams Provider — Core TeamsChannelProvider class.

Outbound: Incoming Webhooks with Adaptive Cards.
Inbound: Bot Framework (optional, for bidirectional).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional

from ..._formatter import (
    MessageFormatter,
    build_teams_adaptive_card,
    build_teams_confirmation_card,
    format_teams_message,
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
    _DEFAULT_API_URL,
    _MAX_RETRIES,
    _RETRY_BASE_DELAY,
    _WEBHOOK_TIMEOUT,
)

logger = logging.getLogger("zenic_agents.channels.teams")


class TeamsChannelProvider:
    """Microsoft Teams channel provider.

    Supports:
      - Outbound via Incoming Webhooks (Adaptive Cards)
      - Optional inbound via Bot Framework
      - Interactive confirmations via ActionCard
      - Dry-run mode when unconfigured
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> None:
        self._webhook_url = webhook_url or os.environ.get("TEAMS_WEBHOOK_URL", "")
        self._bot_token = bot_token or os.environ.get("TEAMS_BOT_TOKEN", "")
        self._api_url = api_url or os.environ.get("TEAMS_API_URL", _DEFAULT_API_URL)
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()
        self._message_handler: Optional[MessageHandler] = None
        self._confirmation_handler: Optional[ConfirmationHandler] = None
        self._session: Optional[Any] = None

    @property
    def name(self) -> str:
        return "teams"

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
        return bool(self._webhook_url)

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send a message to Microsoft Teams via Incoming Webhook."""
        if not self._webhook_url:
            return self._dry_run_send(message)

        payload = format_teams_message(message)
        response = await self._post_webhook(payload)

        with self._lock:
            self._sent_count += 1 if response.success else 0
            self._failed_count += 0 if response.success else 1

        return response

    async def send_confirmation(
        self, request: ConfirmationRequest
    ) -> ChannelResponse:
        """Send an interactive confirmation via Teams ActionCard."""
        if not self._webhook_url:
            return self._dry_run_confirmation(request)

        card = build_teams_confirmation_card(request)
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": card,
                }
            ],
        }

        response = await self._post_webhook(payload)

        with self._lock:
            self._confirmation_count += 1

        return response

    async def start(self) -> None:
        """Initialize the provider."""
        if self._started:
            return

        if _HAS_AIOHTTP and not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_WEBHOOK_TIMEOUT),
            )

        self._started = True
        logger.info("TeamsChannelProvider: started (webhook=%s)", bool(self._webhook_url))

    async def stop(self) -> None:
        """Gracefully shut down the provider."""
        if self._session and _HAS_AIOHTTP:
            await self._session.close()
            self._session = None
        self._started = False
        logger.info("TeamsChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": "teams",
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "is_available": self.is_available,
                "has_webhook": bool(self._webhook_url),
                "has_bot_token": bool(self._bot_token),
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

    # ── Internal: HTTP ──────────────────────────────────────────

    async def _post_webhook(self, payload: Dict[str, Any]) -> ChannelResponse:
        """POST a payload to the Teams Incoming Webhook."""
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_aiohttp(data)
                elif _HAS_URLLIB:
                    return await self._post_urllib(data)
                else:
                    return ChannelResponse(
                        success=False, channel="teams",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "TeamsChannelProvider: attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt, _MAX_RETRIES, e, delay,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    return ChannelResponse(
                        success=False, channel="teams",
                        status=DeliveryStatus.FAILED,
                        error=f"HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False, channel="teams",
            status=DeliveryStatus.FAILED,
            error="Unexpected retry loop exit",
            timestamp=time.time(),
        )

    async def _post_aiohttp(self, data: bytes) -> ChannelResponse:
        """Send via aiohttp ClientSession."""
        assert self._session is not None
        headers = {"Content-Type": "application/json"}
        async with self._session.post(
            self._webhook_url, data=data, headers=headers,
        ) as resp:
            body = await resp.text()

            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset_at = resp.headers.get("X-RateLimit-Reset")
            if remaining is not None:
                self._rate_limit_info = RateLimitInfo(
                    remaining=int(remaining),
                    reset_at=float(reset_at) if reset_at else 0.0,
                    limit=int(resp.headers.get("X-RateLimit-Limit", -1)),
                )

            if resp.status in (200, 202):
                return ChannelResponse(
                    success=True, channel="teams",
                    status=DeliveryStatus.SENT,
                    metadata={"http_status": resp.status, "body": body[:200]},
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                self._rate_limit_info = RateLimitInfo(remaining=0, reset_at=time.time() + retry_after)
                return ChannelResponse(
                    success=False, channel="teams",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"Rate limited. Retry after {retry_after}s",
                    timestamp=time.time(),
                )
            else:
                return ChannelResponse(
                    success=False, channel="teams",
                    status=DeliveryStatus.FAILED,
                    error=f"HTTP {resp.status}: {body[:200]}",
                    timestamp=time.time(),
                )

    async def _post_urllib(self, data: bytes) -> ChannelResponse:
        """Send via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio

        def _sync_post() -> ChannelResponse:
            validated_url = _validate_url(self._webhook_url)
            req = urllib.request.Request(
                validated_url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_WEBHOOK_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return ChannelResponse(
                        success=True, channel="teams",
                        status=DeliveryStatus.SENT,
                        metadata={"http_status": resp.status, "body": body[:200]},
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    retry_after = float(e.headers.get("Retry-After", "5"))
                    return ChannelResponse(
                        success=False, channel="teams",
                        status=DeliveryStatus.RATE_LIMITED,
                        error=f"Rate limited. Retry after {retry_after}s",
                        timestamp=time.time(),
                    )
                body = e.read().decode("utf-8", errors="replace")[:200]
                return ChannelResponse(
                    success=False, channel="teams",
                    status=DeliveryStatus.FAILED,
                    error=f"HTTP {e.code}: {body}",
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False, channel="teams",
                    status=DeliveryStatus.FAILED,
                    error=f"urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    # ── Internal: Dry Run ───────────────────────────────────────

    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        with self._lock:
            self._sent_count += 1
        text_preview = (message.text or message.html or "")[:200]
        logger.info(
            "[TEAMS DRY-RUN] To: %s | Subject: %s | Text: %s",
            message.recipient or "default",
            message.subject or "(none)",
            text_preview,
        )
        return ChannelResponse(
            success=True, channel="teams",
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
            "[TEAMS DRY-RUN] Confirmation: %s | Options: %s",
            request.title, list(request.options),
        )
        return ChannelResponse(
            success=True, channel="teams",
            status=DeliveryStatus.DRY_RUN,
            metadata={"mode": "dry_run", "action_id": request.action_id},
            timestamp=time.time(),
        )
