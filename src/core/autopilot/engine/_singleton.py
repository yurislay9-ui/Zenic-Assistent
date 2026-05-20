"""ZENIC-AGENTS - Autopilot Engine: Singleton Accessors

Provides the global singleton get/reset functions for AutopilotEngine.
"""

from __future__ import annotations

import threading
from typing import Optional


_autopilot_engine_instance: Optional[Any] = None
_autopilot_engine_lock = threading.Lock()


def get_autopilot_engine(db_path: str = "autopilot_engine.sqlite"):
    """Get or create the global AutopilotEngine instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton AutopilotEngine instance.
    """
    global _autopilot_engine_instance
    with _autopilot_engine_lock:
        if _autopilot_engine_instance is None:
            # Local import to avoid circular dependency at module load time
            from .core import AutopilotEngine
            _autopilot_engine_instance = AutopilotEngine(db_path=db_path)
        return _autopilot_engine_instance


def reset_autopilot_engine() -> None:
    """Reset the global AutopilotEngine instance (for testing)."""
    global _autopilot_engine_instance
    with _autopilot_engine_lock:
        _autopilot_engine_instance = None
