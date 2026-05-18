"""Re-exports for feedback package."""

from ._types import *
from ._helpers import *
from ._mixin_core import *

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_closed_loop_feedback_instance: Optional[ClosedLoopFeedback] = None
_closed_loop_feedback_lock = threading.Lock()


def get_closed_loop_feedback(
    db_path: str = "autopilot_feedback.sqlite",
    max_cycles_without_improvement: int = 3,
) -> ClosedLoopFeedback:
    """Get or create the global ClosedLoopFeedback instance.

    Args:
        db_path: Path to the SQLite database file.
        max_cycles_without_improvement: Max cycles without improvement before escalation.

    Returns:
        The singleton ClosedLoopFeedback instance.
    """
    global _closed_loop_feedback_instance
    with _closed_loop_feedback_lock:
        if _closed_loop_feedback_instance is None:
            _closed_loop_feedback_instance = ClosedLoopFeedback(
                db_path=db_path,
                max_cycles_without_improvement=max_cycles_without_improvement,
            )
        return _closed_loop_feedback_instance


def reset_closed_loop_feedback() -> None:
    """Reset the global ClosedLoopFeedback instance (for testing)."""
    global _closed_loop_feedback_instance
    with _closed_loop_feedback_lock:
        _closed_loop_feedback_instance = None



__all__ = [
    "FeedbackAction",
    "FeedbackCycle",
    "ClosedLoopFeedback",
    "get_closed_loop_feedback",
    "reset_closed_loop_feedback",
]