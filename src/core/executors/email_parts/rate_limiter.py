"""
ZENIC-AGENTS — Email Rate Limiter (Phase 2)

Per-recipient and global email rate limiting to prevent spam
and comply with provider sending limits.

Features:
  - Sliding window counters for accurate rate tracking
  - Per-recipient limits (minute, hour, day)
  - Global limits (minute, hour, day)
  - Cooldown enforcement (minimum time between sends to same recipient)
  - Burst allowance for short bursts of emails
  - No external dependencies
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.email_parts.rate_limiter")


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class RateLimitConfig:
    """Configuration for email rate limiting.

    All limits are counts per time window. Set to 0 to disable
    a specific limit. Cooldown and burst settings provide
    fine-grained control over send pacing.
    """
    max_per_recipient_per_minute: int = 5
    max_per_recipient_per_hour: int = 20
    max_per_recipient_per_day: int = 100
    max_global_per_minute: int = 30
    max_global_per_hour: int = 500
    max_global_per_day: int = 5000
    cooldown_seconds: float = 2.0          # Min time between emails to same recipient
    burst_allowance: int = 3               # Allow short bursts up to N emails in 10s


@dataclass
class RateLimitResult:
    """Result of a rate limit check for a single recipient.

    Attributes:
        allowed: Whether the email is allowed to be sent.
        reason: Human-readable reason if denied (empty if allowed).
        retry_after_seconds: Seconds until the recipient can receive another email.
        recipient: The recipient email address.
        current_count: Current send count in the limiting window.
        limit: The limit that was hit (if denied).
    """
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
    """Memory-efficient sliding window counter using timestamp lists.

    Automatically prunes expired events during count_in_window()
    calls, so memory usage is bounded by the window size × event rate.
    """

    def __init__(self) -> None:
        self._events: List[float] = []

    def add(self, timestamp: float) -> None:
        """Record an event at the given timestamp."""
        self._events.append(timestamp)

    def count_in_window(self, window_seconds: float, now: float) -> int:
        """Count events within the sliding window.

        Prunes expired events as a side effect, keeping memory bounded.
        """
        cutoff = now - window_seconds
        self._events = [t for t in self._events if t > cutoff]
        return len(self._events)

    def time_since_last(self, now: float) -> float:
        """Get seconds since the last event, or infinity if no events."""
        if not self._events:
            return float("inf")
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
      - Spamming a single recipient (per-recipient limits)
      - Exceeding global sending limits (provider quotas)
      - Sending too fast (burst protection)
      - Email flooding (cooldown enforcement)

    Uses per-recipient sliding window counters and a global counter.
    All counters auto-prune expired events during checks.

    Usage:
        limiter = EmailRateLimiter()
        results = limiter.check(["user@example.com"])
        if all(r.allowed for r in results):
            # Send the email
            limiter.record_send(["user@example.com"])
        else:
            # Rate limited — check retry_after_seconds
            for r in results:
                if not r.allowed:
                    print(f"Rate limited: {r.reason}, retry after {r.retry_after_seconds}s")
    """

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self._config = config or RateLimitConfig()
        self._recipient_counters: Dict[str, _SlidingWindowCounter] = {}
        self._global_counter = _SlidingWindowCounter()
        self._burst_counters: Dict[str, _SlidingWindowCounter] = {}
        self._denied_count: int = 0
        self._allowed_count: int = 0

    def check(self, recipients: List[str]) -> List[RateLimitResult]:
        """Check if emails can be sent to the given recipients.

        Evaluates global limits first (short-circuits if exceeded),
        then checks per-recipient limits. Returns one RateLimitResult
        per recipient.

        Args:
            recipients: List of recipient email addresses.

        Returns:
            List of RateLimitResult, one per recipient. If global
            limits are exceeded, returns a single result with the
            global limit reason (no per-recipient checks performed).
        """
        now = time.time()
        results: List[RateLimitResult] = []

        # ── Global limits (short-circuit if exceeded) ──────────
        global_result = self._check_global(now)
        if global_result is not None:
            results.append(global_result)
            self._denied_count += 1
            return results  # Short circuit — global limit hit

        # ── Per-recipient limits ───────────────────────────────
        for recipient in recipients:
            result = self._check_recipient(recipient, now)
            results.append(result)

        return results

    def record_send(self, recipients: List[str]) -> None:
        """Record that emails were sent to the given recipients.

        Call this AFTER successfully sending emails to update the
        rate limit counters.

        Args:
            recipients: List of recipient email addresses.
        """
        now = time.time()
        for recipient in recipients:
            counter = self._recipient_counters.setdefault(recipient, _SlidingWindowCounter())
            counter.add(now)
            burst = self._burst_counters.setdefault(recipient, _SlidingWindowCounter())
            burst.add(now)
        self._global_counter.add(now)
        self._allowed_count += 1

    def get_cooldown_remaining(self, recipient: str) -> float:
        """Get seconds until cooldown expires for a recipient.

        Args:
            recipient: The recipient email address.

        Returns:
            Seconds remaining in cooldown, or 0.0 if not in cooldown.
        """
        now = time.time()
        counter = self._recipient_counters.get(recipient)
        if not counter:
            return 0.0
        elapsed = counter.time_since_last(now)
        if elapsed >= self._config.cooldown_seconds:
            return 0.0
        return self._config.cooldown_seconds - elapsed

    def reset(self) -> None:
        """Reset all rate limit counters and statistics.

        Clears per-recipient counters, global counters, burst counters,
        and resets denied/allowed counts.
        """
        self._recipient_counters.clear()
        self._global_counter.clear()
        self._burst_counters.clear()
        self._denied_count = 0
        self._allowed_count = 0
        logger.info("EmailRateLimiter: All counters reset")

    @property
    def stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics.

        Returns:
            Dict with allowed/denied counts and tracked recipient count.
        """
        return {
            "allowed": self._allowed_count,
            "denied": self._denied_count,
            "tracked_recipients": len(self._recipient_counters),
            "config": {
                "max_per_recipient_per_minute": self._config.max_per_recipient_per_minute,
                "max_per_recipient_per_hour": self._config.max_per_recipient_per_hour,
                "max_per_recipient_per_day": self._config.max_per_recipient_per_day,
                "max_global_per_minute": self._config.max_global_per_minute,
                "max_global_per_hour": self._config.max_global_per_hour,
                "max_global_per_day": self._config.max_global_per_day,
                "cooldown_seconds": self._config.cooldown_seconds,
                "burst_allowance": self._config.burst_allowance,
            },
        }

    # ── Private: Global Limit Check ───────────────────────────

    def _check_global(self, now: float) -> Optional[RateLimitResult]:
        """Check global rate limits. Returns None if all pass."""
        count_min = self._global_counter.count_in_window(60, now)
        if count_min >= self._config.max_global_per_minute:
            return RateLimitResult(
                allowed=False,
                reason=(
                    f"Global rate limit: {count_min}/"
                    f"{self._config.max_global_per_minute} per minute"
                ),
                retry_after_seconds=60 - (now % 60),
                current_count=count_min,
                limit=self._config.max_global_per_minute,
            )

        count_hour = self._global_counter.count_in_window(3600, now)
        if count_hour >= self._config.max_global_per_hour:
            return RateLimitResult(
                allowed=False,
                reason=(
                    f"Global rate limit: {count_hour}/"
                    f"{self._config.max_global_per_hour} per hour"
                ),
                retry_after_seconds=3600 - (now % 3600),
                current_count=count_hour,
                limit=self._config.max_global_per_hour,
            )

        count_day = self._global_counter.count_in_window(86400, now)
        if count_day >= self._config.max_global_per_day:
            return RateLimitResult(
                allowed=False,
                reason=(
                    f"Global rate limit: {count_day}/"
                    f"{self._config.max_global_per_day} per day"
                ),
                retry_after_seconds=86400 - (now % 86400),
                current_count=count_day,
                limit=self._config.max_global_per_day,
            )

        return None

    # ── Private: Per-Recipient Limit Check ────────────────────

    def _check_recipient(self, recipient: str, now: float) -> RateLimitResult:
        """Check rate limits for a single recipient."""
        counter = self._recipient_counters.setdefault(recipient, _SlidingWindowCounter())

        # Per-minute limit
        count_min = counter.count_in_window(60, now)
        if count_min >= self._config.max_per_recipient_per_minute:
            self._denied_count += 1
            return RateLimitResult(
                allowed=False,
                reason=(
                    f"Recipient {recipient}: {count_min}/"
                    f"{self._config.max_per_recipient_per_minute} per minute"
                ),
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
                reason=(
                    f"Recipient {recipient}: {count_hour}/"
                    f"{self._config.max_per_recipient_per_hour} per hour"
                ),
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
                reason=(
                    f"Recipient {recipient}: {count_day}/"
                    f"{self._config.max_per_recipient_per_day} per day"
                ),
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
            burst = self._burst_counters.setdefault(recipient, _SlidingWindowCounter())
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
