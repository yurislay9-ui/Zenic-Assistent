"""
ZENIC-AGENTS — Adapter Registry

Dynamic registry for channel providers, mirroring the ExecutorRegistry pattern.
Manages provider registration, lookup, lifecycle (start/stop), and
fallback-based message delivery.

Design invariants:
  1. Thread-safe — all mutations use RLock.
  2. Never raises on send — always returns ChannelResponse.
  3. 'log' provider is always registered as terminal fallback.
  4. Provider registration is idempotent.
  5. send_with_fallback() never fails — at minimum, logs the message.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional, Set

from ._protocol import ChannelProvider, InboundChannelProvider
from ._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ChannelPriority,
    ConfirmationHandler,
    ConfirmationRequest,
    DeliveryStatus,
    MessageHandler,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.registry")


# ──────────────────────────────────────────────────────────────
#  ADAPTER REGISTRY
# ──────────────────────────────────────────────────────────────

class AdapterRegistry:
    """Central registry for all channel providers.

    Pattern: mirrors ExecutorRegistry — string-keyed, dynamic registration,
    singleton access, safety integration.

    Features:
      - Register/unregister providers by name
      - Alias support (multiple names → same provider)
      - Fallback routing: try primary → fallback chain → log
      - Inbound provider lifecycle management
      - Thread-safe
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._providers: Dict[str, ChannelProvider] = {}
        self._inbound_providers: Dict[str, InboundChannelProvider] = {}
        self._fallback_map: Dict[str, List[str]] = {}  # channel → [fallback_chain]
        self._stats = {
            "total_sent": 0,
            "total_sent_success": 0,
            "total_sent_failed": 0,
            "total_fallback_used": 0,
        }

    # ── Registration ────────────────────────────────────────────

    def register(
        self,
        provider: ChannelProvider,
        aliases: Optional[List[str]] = None,
    ) -> None:
        """Register a channel provider.

        Args:
            provider: The ChannelProvider instance.
            aliases: Optional alternative names for the same provider.
        """
        with self._lock:
            name = provider.name
            self._providers[name] = provider

            if isinstance(provider, InboundChannelProvider):
                self._inbound_providers[name] = provider

            if aliases:
                for alias in aliases:
                    self._providers[alias] = provider
                    if isinstance(provider, InboundChannelProvider):
                        self._inbound_providers[alias] = provider

            logger.debug(
                "AdapterRegistry: registered provider '%s' (aliases=%s)",
                name, aliases,
            )

    def unregister(self, name: str) -> bool:
        """Unregister a provider by name.

        Returns:
            True if found and removed, False otherwise.
        """
        with self._lock:
            provider = self._providers.pop(name, None)
            self._inbound_providers.pop(name, None)

            if provider is None:
                return False

            # Also remove aliases pointing to the same provider
            to_remove = [
                k for k, v in self._providers.items()
                if v is provider and k != name
            ]
            for k in to_remove:
                del self._providers[k]
                self._inbound_providers.pop(k, None)

            logger.info("AdapterRegistry: unregistered provider '%s'", name)
            return True

    def get(self, name: str) -> Optional[ChannelProvider]:
        """Get a provider by name."""
        with self._lock:
            return self._providers.get(name)

    # ── Fallback Configuration ──────────────────────────────────

    def set_fallback_chain(self, channel: str, fallbacks: List[str]) -> None:
        """Set the fallback chain for a channel.

        When send_with_fallback() is called and the primary channel fails,
        it tries each fallback in order until one succeeds.
        The 'log' provider should always be the terminal fallback.

        Args:
            channel: Primary channel name.
            fallbacks: Ordered list of fallback channel names.
        """
        with self._lock:
            self._fallback_map[channel] = fallbacks
            logger.debug(
                "AdapterRegistry: set fallback for '%s' → %s",
                channel, fallbacks,
            )

    def get_fallback_chain(self, channel: str) -> List[str]:
        """Get the fallback chain for a channel."""
        with self._lock:
            return list(self._fallback_map.get(channel, []))

    # ── Send ────────────────────────────────────────────────────

    async def send(
        self,
        channel: str,
        message: ChannelMessage,
    ) -> ChannelResponse:
        """Send a message through a specific channel.

        If the channel is not available, returns a failed ChannelResponse.
        NEVER raises.

        Args:
            channel: Provider name to send through.
            message: Universal message envelope.

        Returns:
            ChannelResponse with delivery result.
        """
        with self._lock:
            self._stats["total_sent"] += 1

        provider = self.get(channel)
        if provider is None:
            logger.warning("AdapterRegistry: no provider for channel '%s'", channel)
            return ChannelResponse(
                success=False,
                channel=channel,
                status=DeliveryStatus.FAILED,
                error=f"No provider registered for channel '{channel}'",
                timestamp=time.time(),
            )

        if not provider.is_available:
            logger.warning("AdapterRegistry: provider '%s' is not available", channel)
            return ChannelResponse(
                success=False,
                channel=channel,
                status=DeliveryStatus.FAILED,
                error=f"Provider '{channel}' is not available",
                timestamp=time.time(),
            )

        try:
            response = await provider.send(message)
            with self._lock:
                if response.success:
                    self._stats["total_sent_success"] += 1
                else:
                    self._stats["total_sent_failed"] += 1
            return response
        except Exception as e:
            logger.error(
                "AdapterRegistry: error sending via '%s': %s", channel, e,
            )
            with self._lock:
                self._stats["total_sent_failed"] += 1
            return ChannelResponse(
                success=False,
                channel=channel,
                status=DeliveryStatus.FAILED,
                error=f"Provider error: {e}",
                timestamp=time.time(),
            )

    async def send_with_fallback(
        self,
        channel: str,
        message: ChannelMessage,
        exclude_channels: Optional[Set[str]] = None,
    ) -> ChannelResponse:
        """Send a message with automatic fallback chain.

        Tries the primary channel, then each fallback in order.
        Always succeeds at minimum via the 'log' provider.

        Args:
            channel: Primary provider name.
            message: Universal message envelope.
            exclude_channels: Channels to skip (e.g., if they just failed).

        Returns:
            ChannelResponse from the first successful delivery,
            or from the last attempted channel.
        """
        exclude = exclude_channels or set()
        chain = [channel] + self.get_fallback_chain(channel)

        last_response: Optional[ChannelResponse] = None

        for ch in chain:
            if ch in exclude:
                continue

            provider = self.get(ch)
            if provider is None or not provider.is_available:
                continue

            response = await self.send(ch, message)
            last_response = response

            if response.success:
                if ch != channel:
                    with self._lock:
                        self._stats["total_fallback_used"] += 1
                    # Mark as fallback delivery
                    return ChannelResponse(
                        success=True,
                        channel=response.channel,
                        message_id=response.message_id,
                        status=DeliveryStatus.FALLBACK,
                        metadata={
                            **response.metadata,
                            "original_channel": channel,
                            "fallback_channel": ch,
                        },
                        timestamp=response.timestamp,
                    )
                return response

        # All fallbacks failed — try log as terminal fallback
        if "log" not in exclude:
            log_provider = self.get("log")
            if log_provider and log_provider.is_available:
                response = await self.send("log", message)
                with self._lock:
                    self._stats["total_fallback_used"] += 1
                return ChannelResponse(
                    success=True,
                    channel="log",
                    status=DeliveryStatus.FALLBACK,
                    metadata={"original_channel": channel, "fallback_channel": "log"},
                    timestamp=time.time(),
                )

        # Absolute failure (shouldn't happen if log is registered)
        return last_response or ChannelResponse(
            success=False,
            channel=channel,
            status=DeliveryStatus.FAILED,
            error="All channels failed, including fallbacks",
            timestamp=time.time(),
        )

    async def send_confirmation(
        self,
        channel: str,
        request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send a confirmation request through a specific channel.

        Falls back to plain text if the channel doesn't support confirmations.

        Args:
            channel: Provider name.
            request: Confirmation request.

        Returns:
            ChannelResponse with the sent message ID.
        """
        provider = self.get(channel)
        if provider is None:
            return ChannelResponse(
                success=False,
                channel=channel,
                status=DeliveryStatus.FAILED,
                error=f"No provider for channel '{channel}'",
                timestamp=time.time(),
            )

        try:
            return await provider.send_confirmation(request)
        except Exception as e:
            logger.error(
                "AdapterRegistry: error sending confirmation via '%s': %s",
                channel, e,
            )
            return ChannelResponse(
                success=False,
                channel=channel,
                status=DeliveryStatus.FAILED,
                error=f"Confirmation error: {e}",
                timestamp=time.time(),
            )

    # ── Inbound Lifecycle ───────────────────────────────────────

    def set_message_handler(
        self,
        channel: str,
        handler: MessageHandler,
    ) -> bool:
        """Register an inbound message handler for a bidirectional provider.

        Returns:
            True if the provider exists and supports inbound, False otherwise.
        """
        with self._lock:
            provider = self._inbound_providers.get(channel)
            if provider is None:
                logger.warning(
                    "AdapterRegistry: no inbound provider for '%s'", channel,
                )
                return False
            provider.set_message_handler(handler)
            return True

    def set_confirmation_handler(
        self,
        channel: str,
        handler: ConfirmationHandler,
    ) -> bool:
        """Register an inbound confirmation handler for a bidirectional provider.

        Returns:
            True if the provider exists and supports inbound, False otherwise.
        """
        with self._lock:
            provider = self._inbound_providers.get(channel)
            if provider is None:
                logger.warning(
                    "AdapterRegistry: no inbound provider for '%s'", channel,
                )
                return False
            provider.set_confirmation_handler(handler)
            return True

    async def start_inbound(self, channel: str = "") -> None:
        """Start listening for inbound messages.

        Args:
            channel: If provided, start only this provider.
                     If empty, start all inbound providers.
        """
        with self._lock:
            providers = (
                {channel: self._inbound_providers[channel]}
                if channel and channel in self._inbound_providers
                else dict(self._inbound_providers)
            )

        for name, provider in providers.items():
            try:
                await provider.start()
                logger.info("AdapterRegistry: started inbound provider '%s'", name)
            except Exception as e:
                logger.error(
                    "AdapterRegistry: failed to start '%s': %s", name, e,
                )

    async def stop_all(self) -> None:
        """Stop all providers (inbound and outbound)."""
        with self._lock:
            providers = list(self._providers.values())

        # Deduplicate (aliases point to same instance)
        seen: Set[int] = set()
        unique_providers: List[ChannelProvider] = []
        for p in providers:
            if id(p) not in seen:
                seen.add(id(p))
                unique_providers.append(p)

        for provider in unique_providers:
            try:
                await provider.stop()
            except Exception as e:
                logger.error(
                    "AdapterRegistry: error stopping '%s': %s",
                    provider.name, e,
                )

    # ── Query ───────────────────────────────────────────────────

    def list_providers(self) -> Dict[str, Dict[str, Any]]:
        """List all registered providers with their status."""
        with self._lock:
            result: Dict[str, Dict[str, Any]] = {}
            seen: Set[int] = set()
            for name, provider in self._providers.items():
                if id(provider) in seen:
                    continue
                seen.add(id(provider))
                result[name] = {
                    "available": provider.is_available,
                    "capabilities": [c.value for c in provider.capabilities],
                    "is_inbound": isinstance(provider, InboundChannelProvider),
                    "stats": provider.stats,
                }
            return result

    def get_providers_by_capability(
        self,
        capability: ChannelCapability,
    ) -> List[ChannelProvider]:
        """Get all providers that support a specific capability."""
        with self._lock:
            seen: Set[int] = set()
            result: List[ChannelProvider] = []
            for provider in self._providers.values():
                if id(provider) not in seen and capability in provider.capabilities:
                    seen.add(id(provider))
                    result.append(provider)
            return result

    @property
    def registered_channels(self) -> List[str]:
        """List of unique registered channel names."""
        with self._lock:
            seen: Set[int] = set()
            names: List[str] = []
            for name, provider in self._providers.items():
                if id(provider) not in seen:
                    seen.add(id(provider))
                    names.append(name)
            return names

    @property
    def stats(self) -> Dict[str, Any]:
        """Registry statistics."""
        with self._lock:
            return {
                **self._stats,
                "registered_channels": len(self.registered_channels),
                "inbound_channels": len(self._inbound_providers),
                "fallback_chains": len(self._fallback_map),
            }


# ──────────────────────────────────────────────────────────────
#  CHANNEL ROUTER
# ──────────────────────────────────────────────────────────────

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
                # Register the log provider as terminal fallback
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


__all__ = [
    "AdapterRegistry",
    "ChannelRouter",
    "get_default_registry",
    "get_default_router",
    "reset_default_registry",
]
