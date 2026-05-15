"""
ZENIC-AGENTS — Channel Provider Protocol

Defines the structural contract every channel provider must satisfy.
Uses typing.Protocol for structural subtyping — providers don't need
to inherit from a base class, they just need to implement the methods.

Two protocols:
  1. ChannelProvider       — Outbound-only (send messages, confirmations)
  2. InboundChannelProvider — Bidirectional (adds receive/handler registration)

Design invariants:
  1. Protocol methods are async — all I/O is non-blocking.
  2. No provider-specific exceptions leak through the protocol.
  3. start()/stop() are idempotent — safe to call multiple times.
  4. stats property is always available for monitoring.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Protocol, runtime_checkable

from ._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationHandler,
    ConfirmationRequest,
    MessageHandler,
    RateLimitInfo,
)


# ──────────────────────────────────────────────────────────────
#  OUTBOUND-ONLY PROVIDER
# ──────────────────────────────────────────────────────────────

@runtime_checkable
class ChannelProvider(Protocol):
    """Protocol for outbound-only channel providers.

    Every channel must implement at least these methods.
    Use InboundChannelProvider for bidirectional channels.
    """

    @property
    def name(self) -> str:
        """Unique channel identifier (e.g. 'teams', 'slack', 'whatsapp')."""
        ...

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        """Set of capabilities this provider supports."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this provider is currently operational.

        Returns False if:
          - Not configured (missing API keys/tokens)
          - Rate limited
          - Connection failed
          - Explicitly disabled
        """
        ...

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send a message through this channel.

        Args:
            message: Universal message envelope.

        Returns:
            ChannelResponse with success/failure and metadata.
            NEVER raises — always returns a response.
        """
        ...

    async def send_confirmation(
        self, request: ConfirmationRequest
    ) -> ChannelResponse:
        """Send an interactive confirmation request.

        If the channel doesn't support interactive elements,
        falls back to a plain text message with instructions.

        Args:
            request: Confirmation request with options.

        Returns:
            ChannelResponse with the sent message ID (for callback matching).
        """
        ...

    async def start(self) -> None:
        """Initialize the provider (open connections, start polling, etc).

        Idempotent — safe to call multiple times.
        """
        ...

    async def stop(self) -> None:
        """Gracefully shut down the provider.

        Idempotent — safe to call multiple times.
        """
        ...

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics for monitoring and health checks."""
        ...

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        """Current rate limit status."""
        ...


# ──────────────────────────────────────────────────────────────
#  BIDIRECTIONAL PROVIDER
# ──────────────────────────────────────────────────────────────

@runtime_checkable
class InboundChannelProvider(ChannelProvider, Protocol):
    """Protocol for bidirectional channel providers (inbound + outbound).

    Extends ChannelProvider with:
      - Message handler registration (for incoming user messages)
      - Confirmation handler registration (for button/callback responses)
      - Inbound polling/webhook loop management
    """

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register a handler for incoming user messages.

        Called whenever a user sends a message through this channel.

        Args:
            handler: Async callback that receives ChannelMessage
                     and returns ChannelResponse.
        """
        ...

    def set_confirmation_handler(self, handler: ConfirmationHandler) -> None:
        """Register a handler for confirmation responses.

        Called whenever a user clicks a confirmation button or
        replies to a confirmation request.

        Args:
            handler: Async callback that receives ConfirmationResult
                     and returns an arbitrary dict.
        """
        ...

    @property
    def is_listening(self) -> bool:
        """Whether the provider is actively listening for inbound messages."""
        ...


# ──────────────────────────────────────────────────────────────
#  PROVIDER CAPABILITY CHECKS
# ──────────────────────────────────────────────────────────────

def has_capability(provider: ChannelProvider, cap: ChannelCapability) -> bool:
    """Check if a provider has a specific capability."""
    return cap in provider.capabilities


def requires_inbound(provider: ChannelProvider) -> bool:
    """Check if a provider supports inbound (bidirectional) communication."""
    return isinstance(provider, InboundChannelProvider)


def can_send_confirmation(provider: ChannelProvider) -> bool:
    """Check if a provider can send interactive confirmations."""
    return ChannelCapability.SEND_CONFIRMATION in provider.capabilities


# ──────────────────────────────────────────────────────────────
#  PUBLIC EXPORTS
# ──────────────────────────────────────────────────────────────

__all__ = [
    "ChannelProvider",
    "InboundChannelProvider",
    "has_capability",
    "requires_inbound",
    "can_send_confirmation",
]
