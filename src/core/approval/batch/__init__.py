"""
Zenic-Agents Asistente - Batch Approval Engine (Phase C3)

Approve or reject multiple similar actions at once. A batch groups
identical-type approval requests so that an approver can act on all
of them in a single operation, with optional partial approval support.
"""

from ._types import BatchRequest, BatchResult, _MAX_RETRIES, _RETRY_DELAY
from ._mixin_core import BatchApprovalEngine

# ── Singleton ─────────────────────────────────────────────

import threading
from typing import Optional

_batch_instance: Optional[BatchApprovalEngine] = None
_batch_lock = threading.Lock()


def get_batch_approval(db_path: str = "batch_approval.sqlite") -> BatchApprovalEngine:
    """Get or create the global BatchApprovalEngine instance."""
    global _batch_instance
    with _batch_lock:
        if _batch_instance is None:
            _batch_instance = BatchApprovalEngine(db_path=db_path)
        return _batch_instance


def reset_batch_approval() -> None:
    """Reset the global BatchApprovalEngine (for testing)."""
    global _batch_instance
    _batch_instance = None


__all__ = [
    "BatchRequest",
    "BatchResult",
    "BatchApprovalEngine",
    "get_batch_approval",
    "reset_batch_approval",
]
