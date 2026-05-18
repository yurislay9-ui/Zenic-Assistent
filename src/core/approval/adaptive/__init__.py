"""
Zenic-Agents Asistente - Adaptive Approval Engine (Phase C3)

Learns from past approval decisions to auto-approve repetitive safe actions.
When a user consistently approves the same type of action, the engine
automatically approves future occurrences after a configurable threshold
of consecutive approvals.
"""

from ._types import (
    AdaptiveApprovalRecord,
    _FINANCIAL_KEYWORDS,
    _MAX_RETRIES,
    _RETRY_DELAY,
    _hash_config,
)
from ._mixin_core import AdaptiveApprovalEngine

# ── Singleton ─────────────────────────────────────────────

import threading
from typing import Optional

_adaptive_instance: Optional[AdaptiveApprovalEngine] = None
_adaptive_lock = threading.Lock()


def get_adaptive_approval(
    db_path: str = "adaptive_approval.sqlite",
    auto_approve_threshold: int = 5,
) -> AdaptiveApprovalEngine:
    """Get or create the global AdaptiveApprovalEngine instance."""
    global _adaptive_instance
    with _adaptive_lock:
        if _adaptive_instance is None:
            _adaptive_instance = AdaptiveApprovalEngine(
                db_path=db_path,
                auto_approve_threshold=auto_approve_threshold,
            )
        return _adaptive_instance


def reset_adaptive_approval() -> None:
    """Reset the global AdaptiveApprovalEngine (for testing)."""
    global _adaptive_instance
    _adaptive_instance = None


__all__ = [
    "AdaptiveApprovalRecord",
    "AdaptiveApprovalEngine",
    "get_adaptive_approval",
    "reset_adaptive_approval",
]
