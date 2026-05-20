"""
ZENIC-AGENTS — Log Channel Provider

Always-available terminal fallback provider.
Logs all messages at INFO level — no external connections needed.

Design invariants:
  1. Always available — is_available is always True.
  2. Never raises — all operations succeed.
  3. No I/O beyond Python logging.
  4. No external dependencies.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, FrozenSet

from ._protocol import ChannelProvider
from ._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.log_provider")


class LogChannelProvider:
    """Always-available log-based channel provider.

    Terminal fallback: if all real channels fail, messages are logged.
    Useful for debugging, development, and as a safety net.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._confirmation_count: int = 0

    # ── ChannelProvider Protocol ────────────────────────────────

    @property
    def name(self) -> str:
        return "log"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        return frozenset({
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_RICH,
            ChannelCapability.SEND_CONFIRMATION,
        })

    @property
    def is_available(self) -> bool:
        """Always True — logging is always available."""
        return True

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Log the message at INFO level.

        Args:
            message: Universal message envelope.

        Returns:
            ChannelResponse with success=True and DRY_RUN status.
        """
        with self._lock:
            self._sent_count += 1

        recipient = message.recipient or "none"
        text_preview = (message.text or message.html or "")[:200]

        logger.info(
            "[LOG CHANNEL] To: %s | Subject: %s | Text: %s%s",
            recipient,
            message.subject or "(none)",
            text_preview,
            "..." if len(message.text or "") > 200 else "",
        )

        # Log additional fields if present
        if message.fields:
            for f in message.fields[:5]:
                key = f.get("title", f.get("name", ""))
                val = str(f.get("value", ""))[:80]
                logger.info("  └─ %s: %s", key, val)

        return ChannelResponse(
            success=True,
            channel="log",
            message_id=f"log_{self._sent_count}",
            status=DeliveryStatus.DRY_RUN,
            metadata={"logged_at": time.time()},
            timestamp=time.time(),
        )

    async def send_confirmation(
        self, request: ConfirmationRequest
    ) -> ChannelResponse:
        """Log the confirmation request at INFO level.

        Args:
            request: Confirmation request with options.

        Returns:
            ChannelResponse with success=True and DRY_RUN status.
        """
        with self._lock:
            self._confirmation_count += 1

        logger.info(
            "[LOG CHANNEL] Confirmation: %s | Action: %s | Options: %s",
            request.title,
            request.action_id,
            list(request.options),
        )

        return ChannelResponse(
            success=True,
            channel="log",
            message_id=f"log_confirm_{self._confirmation_count}",
            status=DeliveryStatus.DRY_RUN,
            metadata={"logged_at": time.time(), "action_id": request.action_id},
            timestamp=time.time(),
        )

    async def start(self) -> None:
        """No-op — logging is always available."""

    async def stop(self) -> None:
        """No-op — logging cannot be stopped."""

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics."""
        with self._lock:
            return {
                "name": "log",
                "sent_count": self._sent_count,
                "confirmation_count": self._confirmation_count,
                "always_available": True,
            }

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        """Log channel has no rate limits."""
        return RateLimitInfo(remaining=-1, limit=-1)


__all__ = ["LogChannelProvider"]
