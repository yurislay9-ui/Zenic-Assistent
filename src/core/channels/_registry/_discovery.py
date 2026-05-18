"""
ZENIC-AGENTS — Channel Router (Discovery)

Priority-based channel routing with fallback chains.

Decides WHICH channel to use based on message priority,
channel availability, and user preferences.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

from .._types import (
    ChannelMessage,
    ChannelPriority,
    ChannelResponse,
    DeliveryStatus,
)
from ._registry_core import AdapterRegistry
from ._types import _PRIORITY_CHANNEL_MAP, _DEFAULT_FALLBACKS

logger = logging.getLogger("zenic_agents.channels.router")


class ChannelRouter:
    """Priority-based channel routing with fallback chains.

    Decides WHICH channel to use based on message priority,
    channel availability, and user preferences.

    Integration point: NotificationExecutor calls ChannelRouter.route()
    instead of if/elif chains.
    """

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry
        self._user_preferences: Dict[str, List[str]] = {}
        self._priority_overrides: Dict[str, ChannelPriority] = {}

        # Register default fallback chains
        for channel, fallbacks in _DEFAULT_FALLBACKS.items():
            self._registry.set_fallback_chain(channel, fallbacks)

    # ── Routing ─────────────────────────────────────────────────

    def route(
        self,
        priority: ChannelPriority = ChannelPriority.NORMAL,
        alert_type: str = "",
        user_id: str = "",
        exclude_channels: Optional[Set[str]] = None,
    ) -> List[str]:
        """Route a message to the best channel(s) based on priority.

        Args:
            priority: Message priority level.
            alert_type: Optional alert type for specialized routing.
            user_id: Optional user ID for preference-based routing.
            exclude_channels: Channels to exclude from routing.

        Returns:
            Ordered list of channel names to try (primary first).
        """
        exclude = exclude_channels or set()

        # Get candidate channels for this priority
        candidates = list(_PRIORITY_CHANNEL_MAP.get(
            priority, _PRIORITY_CHANNEL_MAP[ChannelPriority.NORMAL],
        ))

        # Apply user preferences if available
        if user_id and user_id in self._user_preferences:
            user_chans = self._user_preferences[user_id]
            # Reorder candidates to match user preference (keep only valid ones)
            preferred = [c for c in user_chans if c in candidates]
            remaining = [c for c in candidates if c not in preferred]
            candidates = preferred + remaining

        # Filter out excluded and unavailable channels
        available: List[str] = []
        for ch in candidates:
            if ch in exclude:
                continue
            provider = self._registry.get(ch)
            if provider is not None and provider.is_available:
                available.append(ch)

        # Ensure at least log is available
        if not available and "log" not in exclude:
            log_provider = self._registry.get("log")
            if log_provider and log_provider.is_available:
                available.append("log")

        return available

    async def route_and_send(
        self,
        message: ChannelMessage,
        alert_type: str = "",
        user_id: str = "",
    ) -> ChannelResponse:
        """Route a message and send it with fallback.

        Convenience method combining route() + send_with_fallback().

        Args:
            message: Universal message envelope (priority determines routing).
            alert_type: Optional alert type for specialized routing.
            user_id: Optional user ID for preference-based routing.

        Returns:
            ChannelResponse from the first successful delivery.
        """
        channels = self.route(
            priority=message.priority,
            alert_type=alert_type,
            user_id=user_id,
        )

        if not channels:
            return ChannelResponse(
                success=False,
                channel="",
                status=DeliveryStatus.FAILED,
                error="No available channels for routing",
                timestamp=time.time(),
            )

        # Try primary channel with fallback
        primary = channels[0]
        return await self._registry.send_with_fallback(primary, message)

    # ── User Preferences ────────────────────────────────────────

    def set_user_preferences(
        self,
        user_id: str,
        channels: List[str],
    ) -> None:
        """Set channel preference order for a user.

        Args:
            user_id: User identifier.
            channels: Ordered list of preferred channel names.
        """
        self._user_preferences[user_id] = channels
        logger.debug(
            "ChannelRouter: set preferences for '%s' → %s",
            user_id, channels,
        )

    def get_user_preferences(self, user_id: str) -> List[str]:
        """Get channel preference order for a user."""
        return list(self._user_preferences.get(user_id, []))

    # ── Priority Overrides ──────────────────────────────────────

    def set_priority_override(
        self,
        alert_type: str,
        priority: ChannelPriority,
    ) -> None:
        """Override the priority for a specific alert type.

        Example: Set 'sna.critical' alerts to EMERGENCY priority
        regardless of the message's default priority.
        """
        self._priority_overrides[alert_type] = priority

    def get_effective_priority(
        self,
        message: ChannelMessage,
        alert_type: str = "",
    ) -> ChannelPriority:
        """Get the effective priority considering overrides."""
        if alert_type and alert_type in self._priority_overrides:
            return self._priority_overrides[alert_type]
        return message.priority

    # ── Properties ──────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Router statistics."""
        return {
            "user_preferences_count": len(self._user_preferences),
            "priority_overrides": len(self._priority_overrides),
            "priority_map": {k.value: v for k, v in _PRIORITY_CHANNEL_MAP.items()},
        }


def get_default_router() -> ChannelRouter:
    """Get a ChannelRouter backed by the default AdapterRegistry."""
    return ChannelRouter(get_default_registry())
