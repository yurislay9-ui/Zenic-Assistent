"""
Zenic-Agents Asistente - Mandatory Justification (Phase 5)

Ensures that every approval or rejection is accompanied by a mandatory
justification. The justification requirements vary by priority level.
"""

from ._types import JustificationRequirement, ApprovalJustification, _MAX_RETRIES, _RETRY_DELAY
from ._mixin_core import JustificationManager

# ── Singleton ─────────────────────────────────────────────

import threading
from typing import Optional

_justification_instance: Optional[JustificationManager] = None
_justification_lock = threading.Lock()


def get_justification_manager(
    db_path: str = "justification.sqlite",
) -> JustificationManager:
    """Get or create the global JustificationManager instance."""
    global _justification_instance
    with _justification_lock:
        if _justification_instance is None:
            _justification_instance = JustificationManager(db_path=db_path)
        return _justification_instance


def reset_justification_manager() -> None:
    """Reset the global JustificationManager (for testing)."""
    global _justification_instance
    _justification_instance = None


__all__ = [
    "JustificationRequirement",
    "ApprovalJustification",
    "JustificationManager",
    "get_justification_manager",
    "reset_justification_manager",
]
