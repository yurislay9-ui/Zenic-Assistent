"""
ZENIC-AGENTS - Channel Router (Phase 3)

Multi-channel notification routing with priority-based selection
and automatic fallback chains.

Routes notifications to the best available channel based on:
  - Alert type/priority (critical → telegram, info → log)
  - Channel availability (configured vs. not)
  - Rate limit status (not rate-limited vs. rate-limited)
  - User preferences (per-user channel preferences)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

class ChannelPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"           # Informational, no urgency
    NORMAL = "normal"     # Standard notification
    HIGH = "high"         # Important, should be seen soon
    URGENT = "urgent"     # Critical, requires immediate attention
    EMERGENCY = "emergency"  # System-down level, all channels


@dataclass
class ChannelConfig:
    """Configuration for a notification channel."""
    name: str                             # telegram, discord, email, webhook, log
    enabled: bool = True
    priority_range: List[ChannelPriority] = field(default_factory=list)  # Empty = all
    max_priority: Optional[ChannelPriority] = None  # Max priority this channel handles
    min_priority: Optional[ChannelPriority] = None  # Min priority this channel handles
    rate_limit_per_hour: int = 60
    fallback_channel: str = ""            # Channel to use if this one fails
    format_support: List[str] = field(default_factory=lambda: ["text", "html"])
    requires_config: List[str] = field(default_factory=list)  # Required env vars


# ──────────────────────────────────────────────────────────────
#  DEFAULT CHANNEL CONFIGS
# ──────────────────────────────────────────────────────────────

DEFAULT_CHANNELS: Dict[str, ChannelConfig] = {
    "log": ChannelConfig(
        name="log",
        enabled=True,
        priority_range=[],  # All priorities
        rate_limit_per_hour=999999,
        fallback_channel="",
        format_support=["text"],
        requires_config=[],
    ),
    "email": ChannelConfig(
        name="email",
        enabled=True,
        priority_range=[ChannelPriority.NORMAL, ChannelPriority.HIGH, ChannelPriority.URGENT],
        rate_limit_per_hour=30,
        fallback_channel="log",
        format_support=["text", "html"],
        requires_config=["SMTP_HOST", "SMTP_USER"],
    ),
    "telegram": ChannelConfig(
        name="telegram",
        enabled=True,
        priority_range=[ChannelPriority.HIGH, ChannelPriority.URGENT, ChannelPriority.EMERGENCY],
        rate_limit_per_hour=30,
        fallback_channel="email",
        format_support=["text", "html"],
        requires_config=["TELEGRAM_BOT_TOKEN"],
    ),
    "discord": ChannelConfig(
        name="discord",
        enabled=True,
        priority_range=[ChannelPriority.NORMAL, ChannelPriority.HIGH],
        rate_limit_per_hour=30,
        fallback_channel="email",
        format_support=["text"],
        requires_config=["DISCORD_WEBHOOK_URL"],
    ),
    "webhook": ChannelConfig(
        name="webhook",
        enabled=True,
        priority_range=[ChannelPriority.NORMAL, ChannelPriority.HIGH],
        rate_limit_per_hour=60,
        fallback_channel="log",
        format_support=["text", "json"],
        requires_config=[],
    ),
}

# Priority ordering for fallback chains
_PRIORITY_ORDER = [
    ChannelPriority.LOW,
    ChannelPriority.NORMAL,
    ChannelPriority.HIGH,
    ChannelPriority.URGENT,
    ChannelPriority.EMERGENCY,
]


# ──────────────────────────────────────────────────────────────
#  CHANNEL ROUTER
# ──────────────────────────────────────────────────────────────

class ChannelRouter:
    """Routes notifications to the best available channel.

    Decision logic:
      1. Filter channels by priority range
      2. Filter by availability (configured and not rate-limited)
      3. Select the highest-priority capable channel
      4. If no channel available, follow fallback chain
      5. Ultimate fallback: log channel (always available)
    """

    def __init__(
        self,
        channels: Optional[Dict[str, ChannelConfig]] = None,
        user_preferences: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._channels = dict(channels or DEFAULT_CHANNELS)
        self._user_preferences = user_preferences or {}
        self._channel_status: Dict[str, str] = {}  # channel → "available"|"unavailable"|"rate_limited"

    def route(
        self,
        priority: ChannelPriority,
        alert_type: str = "",
        user_id: str = "",
        exclude_channels: Optional[List[str]] = None,
    ) -> List[str]:
        """Route a notification to the best channels.

        Returns an ordered list of channel names to try (primary first, fallbacks after).
        """
        exclude = set(exclude_channels or [])

        # Check user preferences
        preferred = self._user_preferences.get(user_id, [])

        # Step 1: Get candidate channels
        candidates = self._get_candidates(priority, exclude)

        # Step 2: Sort by preference and priority handling
        sorted_candidates = self._sort_candidates(candidates, priority, preferred)

        # Step 3: Build result with fallback chain
        result: List[str] = []
        for channel_name in sorted_candidates:
            config = self._channels.get(channel_name)
            if not config or not config.enabled:
                continue
            result.append(channel_name)
            # Add fallback
            if config.fallback_channel and config.fallback_channel not in result:
                result.append(config.fallback_channel)

        # Step 4: Ensure log is always the last fallback
        if "log" not in result:
            result.append("log")

        return result

    def mark_channel_available(self, channel: str) -> None:
        """Mark a channel as available."""
        self._channel_status[channel] = "available"

    def mark_channel_unavailable(self, channel: str, reason: str = "") -> None:
        """Mark a channel as unavailable."""
        self._channel_status[channel] = "unavailable"
        logger.info(f"ChannelRouter: Channel '{channel}' marked unavailable: {reason}")

    def mark_channel_rate_limited(self, channel: str) -> None:
        """Mark a channel as rate-limited."""
        self._channel_status[channel] = "rate_limited"

    def is_channel_available(self, channel: str) -> bool:
        """Check if a channel is available (not unavailable or rate-limited)."""
        status = self._channel_status.get(channel, "available")
        return status == "available"

    def get_channel_config(self, channel: str) -> Optional[ChannelConfig]:
        """Get the configuration for a channel."""
        return self._channels.get(channel)

    def update_channel_config(self, channel: str, config: ChannelConfig) -> None:
        """Update a channel's configuration."""
        self._channels[channel] = config

    def set_user_preference(self, user_id: str, channels: List[str]) -> None:
        """Set channel preferences for a specific user."""
        self._user_preferences[user_id] = channels

    @property
    def available_channels(self) -> List[str]:
        """List currently available channels."""
        return [
            name for name, config in self._channels.items()
            if config.enabled and self.is_channel_available(name)
        ]

    @property
    def stats(self) -> Dict[str, Any]:
        """Get channel router statistics."""
        return {
            "total_channels": len(self._channels),
            "available_channels": len(self.available_channels),
            "channel_status": dict(self._channel_status),
            "users_with_preferences": len(self._user_preferences),
        }

    # ── Private methods ──────────────────────────────────────

    def _get_candidates(
        self, priority: ChannelPriority, exclude: set
    ) -> List[str]:
        """Get candidate channels for a given priority level."""
        candidates = []
        priority_idx = _PRIORITY_ORDER.index(priority)

        for name, config in self._channels.items():
            if name in exclude:
                continue
            if not config.enabled:
                continue

            # Check if channel handles this priority
            if config.priority_range:
                if priority not in config.priority_range:
                    continue
            else:
                # Empty range = handles all priorities
                pass

            # Check min/max priority
            if config.min_priority:
                min_idx = _PRIORITY_ORDER.index(config.min_priority)
                if priority_idx < min_idx:
                    continue
            if config.max_priority:
                max_idx = _PRIORITY_ORDER.index(config.max_priority)
                if priority_idx > max_idx:
                    continue

            candidates.append(name)

        return candidates

    @staticmethod
    def _sort_candidates(
        candidates: List[str],
        priority: ChannelPriority,
        preferred: List[str],
    ) -> List[str]:
        """Sort candidates by preference and suitability."""
        def sort_key(name: str) -> tuple:
            # Preferred channels get higher priority (lower sort value)
            is_preferred = preferred.index(name) if name in preferred else len(preferred)
            # For urgent/emergency, prefer real-time channels
            is_realtime = name in ("telegram", "discord")
            realtime_boost = 0 if (priority in (ChannelPriority.URGENT, ChannelPriority.EMERGENCY) and is_realtime) else 1
            return (realtime_boost, is_preferred, name)

        return sorted(candidates, key=sort_key)
