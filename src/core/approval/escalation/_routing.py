"""
Zenic-Agents Asistente - Escalation Routing (Phase 5)

Singleton access for the EscalationManager.
"""

from __future__ import annotations

import threading
from typing import Optional

from ._escalator import EscalationManager

# ── Singleton ─────────────────────────────────────────────

_escalation_instance: Optional[EscalationManager] = None
_escalation_lock = threading.Lock()


def get_escalation_manager(
    db_path: str = "escalation.sqlite",
) -> EscalationManager:
    """Get or create the global EscalationManager instance."""
    global _escalation_instance
    with _escalation_lock:
        if _escalation_instance is None:
            _escalation_instance = EscalationManager(db_path=db_path)
        return _escalation_instance


def reset_escalation_manager() -> None:
    """Reset the global EscalationManager (for testing)."""
    global _escalation_instance
    _escalation_instance = None
