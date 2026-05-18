"""_registry._router — ChannelRouter class and singleton accessors."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set

from ._adapter import AdapterRegistry
from ._types import (
    ChannelMessage,
    ChannelPriority,
    ChannelResponse,
    DeliveryStatus,
)

logger = logging.getLogger("zenic_agents.channels.registry")

# Priority → channel suitability mapping
_PRIORITY_CHANNEL_MAP: Dict[ChannelPriority, List[str]] = {
    ChannelPriority.LOW: ["log", "email", "push"],
    ChannelPriority.NORMAL: ["log", "email", "push", "teams", "slack"],
    ChannelPriority.HIGH: ["email", "push", "teams", "slack", "sms"],
    ChannelPriority.URGENT: ["sms", "push", "teams", "slack", "email"],
    ChannelPriority.EMERGENCY: ["sms", "whatsapp", "push", "teams", "slack", "email"],
}

# Default fallback chains
_DEFAULT_FALLBACKS: Dict[str, List[str]] = {
    "teams": ["email", "log"],
    "slack": ["email", "log"],
    "whatsapp": ["sms", "email", "log"],
    "sms": ["email", "log"],
    "email": ["push", "log"],
    "push": ["email", "log"],
    "log": [],
}


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
        """Route a message to the best channel(s) based on priority."""
        exclude = exclude_channels or set()

        candidates = list(_PRIORITY_CHANNEL_MAP.get(
            priority, _PRIORITY_CHANNEL_MAP[ChannelPriority.NORMAL],
        ))

        if user_id and user_id in self._user_preferences:
            user_chans = self._user_preferences[user_id]
            preferred = [c for c in user_chans if c in candidates]
            remaining = [c for c in candidates if c not in preferred]
            candidates = preferred + remaining

        available: List[str] = []
        for ch in candidates:
            if ch in exclude:
                continue
            provider = self._registry.get(ch)
            if provider is not None and provider.is_available:
                available.append(ch)

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
        """Route a message and send it with fallback."""
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

        primary = channels[0]
        return await self._registry.send_with_fallback(primary, message)

    # ── User Preferences ────────────────────────────────────────

    def set_user_preferences(self, user_id: str, channels: List[str]) -> None:
        """Set channel preference order for a user."""
        self._user_preferences[user_id] = channels
        logger.debug(
            "ChannelRouter: set preferences for '%s' → %s",
            user_id, channels,
        )

    def get_user_preferences(self, user_id: str) -> List[str]:
        """Get channel preference order for a user."""
        return list(self._user_preferences.get(user_id, []))

    # ── Priority Overrides ──────────────────────────────────────

    def set_priority_override(self, alert_type: str, priority: ChannelPriority) -> None:
        """Override the priority for a specific alert type."""
        self._priority_overrides[alert_type] = priority

    def get_effective_priority(
        self, message: ChannelMessage, alert_type: str = "",
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


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_default_registry: Optional[AdapterRegistry] = None
_registry_lock = threading.Lock()


def get_default_registry() -> AdapterRegistry:
    """Get the singleton AdapterRegistry instance."""
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                _default_registry = AdapterRegistry()
                from ._log_provider import LogChannelProvider
                _default_registry.register(LogChannelProvider())
    return _default_registry


def get_default_router() -> ChannelRouter:
    """Get a ChannelRouter backed by the default AdapterRegistry."""
    return ChannelRouter(get_default_registry())


def reset_default_registry() -> None:
    """Reset the singleton (for testing)."""
    global _default_registry
    with _registry_lock:
        _default_registry = None
