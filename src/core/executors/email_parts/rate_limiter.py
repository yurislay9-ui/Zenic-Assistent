"""
ZENIC-AGENTS - Email Rate Limiter (Phase 3)

Per-recipient and global email rate limiting to prevent spam.
Implements sliding window counters with configurable thresholds.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class RateLimitConfig:
    """Configuration for email rate limiting."""
    max_per_recipient_per_minute: int = 5
    max_per_recipient_per_hour: int = 20
    max_per_recipient_per_day: int = 100
    max_global_per_minute: int = 30
    max_global_per_hour: int = 500
    max_global_per_day: int = 5000
    cooldown_seconds: float = 2.0         # Min time between emails to same recipient
    burst_allowance: int = 3              # Allow short bursts up to N emails


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    reason: str = ""
    retry_after_seconds: float = 0.0
    recipient: str = ""
    current_count: int = 0
    limit: int = 0


# ──────────────────────────────────────────────────────────────
#  SLIDING WINDOW COUNTER
# ──────────────────────────────────────────────────────────────

class _SlidingWindowCounter:
    """Memory-efficient sliding window counter using timestamp lists."""

    def __init__(self) -> None:
        self._events: List[float] = []

    def add(self, timestamp: float) -> None:
        """Record an event at the given timestamp."""
        self._events.append(timestamp)

    def count_in_window(self, window_seconds: float, now: float) -> int:
        """Count events within the sliding window."""
        cutoff = now - window_seconds
        # Prune old events while counting
        self._events = [t for t in self._events if t > cutoff]
        return len(self._events)

    def time_since_last(self, now: float) -> float:
        """Get seconds since the last event, or infinity if no events."""
        if not self._events:
            return float('inf')
        return now - self._events[-1]

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()


# ──────────────────────────────────────────────────────────────
#  EMAIL RATE LIMITER
# ──────────────────────────────────────────────────────────────

class EmailRateLimiter:
    """Rate limiter for email sending.

    Prevents:
      - Spamming a single recipient
      - Exceeding global sending limits
      - Sending too fast (burst protection)
      - Email flooding (no cooldown between sends)

    Uses per-recipient sliding windows and a global counter.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self._config = config or RateLimitConfig()
        self._recipient_counters: Dict[str, _SlidingWindowCounter] = {}
        self._global_counter = _SlidingWindowCounter()
        self._burst_counter: Dict[str, _SlidingWindowCounter] = {}
        self._denied_count: int = 0
        self._allowed_count: int = 0

    def check(self, recipients: List[str]) -> List[RateLimitResult]:
        """Check if emails can be sent to the given recipients.

        Returns a RateLimitResult per recipient.
        If any result is not allowed, the entire batch should be reconsidered.
        """
        now = time.time()
        results: List[RateLimitResult] = []

        # Check global limits first
        global_count_min = self._global_counter.count_in_window(60, now)
        global_count_hour = self._global_counter.count_in_window(3600, now)
        global_count_day = self._global_counter.count_in_window(86400, now)

        if global_count_min >= self._config.max_global_per_minute:
            results.append(RateLimitResult(
                allowed=False,
                reason=f"Global rate limit: {global_count_min}/{self._config.max_global_per_minute} per minute",
                retry_after_seconds=60 - (now % 60),
                current_count=global_count_min,
                limit=self._config.max_global_per_minute,
            ))
            self._denied_count += 1
            return results  # Short circuit — global limit hit

        if global_count_hour >= self._config.max_global_per_hour:
            results.append(RateLimitResult(
                allowed=False,
                reason=f"Global rate limit: {global_count_hour}/{self._config.max_global_per_hour} per hour",
                retry_after_seconds=3600 - (now % 3600),
                current_count=global_count_hour,
                limit=self._config.max_global_per_hour,
            ))
            self._denied_count += 1
            return results

        if global_count_day >= self._config.max_global_per_day:
            results.append(RateLimitResult(
                allowed=False,
                reason=f"Global rate limit: {global_count_day}/{self._config.max_global_per_day} per day",
                retry_after_seconds=86400 - (now % 86400),
                current_count=global_count_day,
                limit=self._config.max_global_per_day,
            ))
            self._denied_count += 1
            return results

        # Check per-recipient limits
        for recipient in recipients:
            result = self._check_recipient(recipient, now)
            results.append(result)

        return results

    def record_send(self, recipients: List[str]) -> None:
        """Record that emails were sent to the given recipients."""
        now = time.time()
        for recipient in recipients:
            counter = self._recipient_counters.setdefault(recipient, _SlidingWindowCounter())
            counter.add(now)
            burst = self._burst_counter.setdefault(recipient, _SlidingWindowCounter())
            burst.add(now)
        self._global_counter.add(now)
        self._allowed_count += 1

    def get_cooldown_remaining(self, recipient: str) -> float:
        """Get seconds until cooldown expires for a recipient."""
        now = time.time()
        counter = self._recipient_counters.get(recipient)
        if not counter:
            return 0.0
        elapsed = counter.time_since_last(now)
        if elapsed >= self._config.cooldown_seconds:
            return 0.0
        return self._config.cooldown_seconds - elapsed

    def reset(self) -> None:
        """Reset all rate limit counters."""
        self._recipient_counters.clear()
        self._global_counter.clear()
        self._burst_counter.clear()
        self._denied_count = 0
        self._allowed_count = 0

    @property
    def stats(self) -> Dict[str, str | int]:
        """Get rate limiter statistics."""
        return {
            "allowed": self._allowed_count,
            "denied": self._denied_count,
            "tracked_recipients": len(self._recipient_counters),
        }

    # ── Private methods ──────────────────────────────────────

    def _check_recipient(self, recipient: str, now: float) -> RateLimitResult:
        """Check rate limits for a single recipient."""
        counter = self._recipient_counters.setdefault(recipient, _SlidingWindowCounter())

        # Per-minute limit
        count_min = counter.count_in_window(60, now)
        if count_min >= self._config.max_per_recipient_per_minute:
            self._denied_count += 1
            return RateLimitResult(
                allowed=False,
                reason=f"Recipient {recipient}: {count_min}/{self._config.max_per_recipient_per_minute} per minute",
                retry_after_seconds=60 - (now % 60),
                recipient=recipient,
                current_count=count_min,
                limit=self._config.max_per_recipient_per_minute,
            )

        # Per-hour limit
        count_hour = counter.count_in_window(3600, now)
        if count_hour >= self._config.max_per_recipient_per_hour:
            self._denied_count += 1
            return RateLimitResult(
                allowed=False,
                reason=f"Recipient {recipient}: {count_hour}/{self._config.max_per_recipient_per_hour} per hour",
                retry_after_seconds=3600 - (now % 3600),
                recipient=recipient,
                current_count=count_hour,
                limit=self._config.max_per_recipient_per_hour,
            )

        # Per-day limit
        count_day = counter.count_in_window(86400, now)
        if count_day >= self._config.max_per_recipient_per_day:
            self._denied_count += 1
            return RateLimitResult(
                allowed=False,
                reason=f"Recipient {recipient}: {count_day}/{self._config.max_per_recipient_per_day} per day",
                retry_after_seconds=86400 - (now % 86400),
                recipient=recipient,
                current_count=count_day,
                limit=self._config.max_per_recipient_per_day,
            )

        # Cooldown check (min time between emails)
        elapsed = counter.time_since_last(now)
        if elapsed < self._config.cooldown_seconds and count_min > 0:
            remaining = self._config.cooldown_seconds - elapsed
            # Allow if within burst allowance
            burst = self._burst_counter.setdefault(recipient, _SlidingWindowCounter())
            burst_count = burst.count_in_window(10, now)  # 10-second burst window
            if burst_count >= self._config.burst_allowance:
                self._denied_count += 1
                return RateLimitResult(
                    allowed=False,
                    reason=f"Recipient {recipient}: cooldown ({remaining:.1f}s remaining)",
                    retry_after_seconds=remaining,
                    recipient=recipient,
                    current_count=count_min,
                    limit=self._config.max_per_recipient_per_minute,
                )

        return RateLimitResult(
            allowed=True,
            recipient=recipient,
            current_count=count_min,
            limit=self._config.max_per_recipient_per_minute,
        )
