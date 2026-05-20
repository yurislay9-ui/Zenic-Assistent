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

from ._registry_core import AdapterRegistry, get_default_registry, reset_default_registry
from ._discovery import ChannelRouter, get_default_router

__all__ = [
    "AdapterRegistry",
    "ChannelRouter",
    "get_default_registry",
    "get_default_router",
    "reset_default_registry",
]
