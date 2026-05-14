"""
ZENIC-AGENTS - Notification Rate Limiter (Phase 3)

Per-channel rate limiting for notifications.
Prevents notification spam across all channels.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class ChannelRateLimit:
    """Rate limit configuration for a channel."""
    channel: str
    max_per_minute: int = 10
    max_per_hour: int = 60
    max_per_day: int = 500
    cooldown_seconds: float = 1.0


@dataclass
class RateLimitCheck:
    """Result of a rate limit check."""
    allowed: bool
    channel: str
    reason: str = ""
    retry_after: float = 0.0
    current_per_minute: int = 0
    current_per_hour: int = 0


# ──────────────────────────────────────────────────────────────
#  NOTIFICATION RATE LIMITER
# ──────────────────────────────────────────────────────────────

class NotificationRateLimiter:
    """Rate limiter for notification dispatch across channels.

    Prevents notification spam by enforcing per-channel limits.
    Uses sliding window counters for accurate rate tracking.
    """

    def __init__(self) -> None:
        self._limits: Dict[str, ChannelRateLimit] = {}
        self._timestamps: Dict[str, List[float]] = {}
        self._denied: int = 0
        self._allowed: int = 0

        # Register default limits
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default rate limits for standard channels."""
        defaults = [
            ChannelRateLimit("log", max_per_minute=999, max_per_hour=9999, max_per_day=99999),
            ChannelRateLimit("email", max_per_minute=5, max_per_hour=30, max_per_day=200),
            ChannelRateLimit("telegram", max_per_minute=5, max_per_hour=30, max_per_day=200),
            ChannelRateLimit("discord", max_per_minute=5, max_per_hour=30, max_per_day=200),
            ChannelRateLimit("webhook", max_per_minute=10, max_per_hour=60, max_per_day=500),
        ]
        for limit in defaults:
            self._limits[limit.channel] = limit

    def configure_channel(self, config: ChannelRateLimit) -> None:
        """Configure rate limits for a specific channel."""
        self._limits[config.channel] = config

    def check(self, channel: str) -> RateLimitCheck:
        """Check if a notification can be sent on the given channel.

        Returns RateLimitCheck with allowed=True if the notification can proceed.
        """
        now = time.time()
        limit = self._limits.get(channel)
        if not limit:
            # No limit configured — allow by default
            return RateLimitCheck(allowed=True, channel=channel)

        key = channel
        self._timestamps.setdefault(key, [])
        # Prune old timestamps
        ts = self._timestamps[key]
        ts[:] = [t for t in ts if now - t < 86400]  # Keep last 24h

        # Count in windows
        per_minute = len([t for t in ts if now - t < 60])
        per_hour = len([t for t in ts if now - t < 3600])
        per_day = len(ts)

        # Check limits
        if per_minute >= limit.max_per_minute:
            self._denied += 1
            return RateLimitCheck(
                allowed=False,
                channel=channel,
                reason=f"Rate limit: {per_minute}/{limit.max_per_minute} per minute",
                retry_after=60 - (now % 60),
                current_per_minute=per_minute,
                current_per_hour=per_hour,
            )

        if per_hour >= limit.max_per_hour:
            self._denied += 1
            return RateLimitCheck(
                allowed=False,
                channel=channel,
                reason=f"Rate limit: {per_hour}/{limit.max_per_hour} per hour",
                retry_after=3600 - (now % 3600),
                current_per_minute=per_minute,
                current_per_hour=per_hour,
            )

        if per_day >= limit.max_per_day:
            self._denied += 1
            return RateLimitCheck(
                allowed=False,
                channel=channel,
                reason=f"Rate limit: {per_day}/{limit.max_per_day} per day",
                retry_after=86400 - (now % 86400),
                current_per_minute=per_minute,
                current_per_hour=per_hour,
            )

        self._allowed += 1
        return RateLimitCheck(
            allowed=True,
            channel=channel,
            current_per_minute=per_minute,
            current_per_hour=per_hour,
        )

    def record_send(self, channel: str) -> None:
        """Record that a notification was sent on a channel."""
        now = time.time()
        key = channel
        self._timestamps.setdefault(key, [])
        self._timestamps[key].append(now)

    def reset(self) -> None:
        """Reset all rate limit counters."""
        self._timestamps.clear()
        self._denied = 0
        self._allowed = 0

    @property
    def stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "allowed": self._allowed,
            "denied": self._denied,
            "configured_channels": list(self._limits.keys()),
        }
