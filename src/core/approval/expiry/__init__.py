"""
Zenic-Agents Asistente - Expiration with Auto-Revert (Phase 5)

Manages expiration of approval requests with configurable TTL and
automatic revert when approvals expire.
"""

from ._types import ExpiryConfig, ExpiryRecord, _MAX_RETRIES, _RETRY_DELAY
from ._mixin_core import ExpiryManager

# ── Singleton ─────────────────────────────────────────────

import threading
from typing import Optional

_expiry_instance: Optional[ExpiryManager] = None
_expiry_lock = threading.Lock()


def get_expiry_manager(
    db_path: str = "expiry.sqlite",
    config: Optional[ExpiryConfig] = None,
) -> ExpiryManager:
    """Get or create the global ExpiryManager instance."""
    global _expiry_instance
    with _expiry_lock:
        if _expiry_instance is None:
            _expiry_instance = ExpiryManager(db_path=db_path, config=config)
        return _expiry_instance


def reset_expiry_manager() -> None:
    """Reset the global ExpiryManager (for testing)."""
    global _expiry_instance
    _expiry_instance = None


__all__ = [
    "ExpiryConfig",
    "ExpiryRecord",
    "ExpiryManager",
    "get_expiry_manager",
    "reset_expiry_manager",
]
