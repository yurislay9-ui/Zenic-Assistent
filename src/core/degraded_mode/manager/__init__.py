"""Re-exports for manager package."""

from ._types import *
from ._mixin_core import *

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

_lock = threading.Lock()
def get_degraded_mode_manager(**kwargs: Any) -> DegradedModeManager:
    """Get or create the global DegradedModeManager instance."""
    global _degraded_mode_manager
    with _lock:
        if _degraded_mode_manager is None:
            _degraded_mode_manager = DegradedModeManager(**kwargs)
        return _degraded_mode_manager


def reset_degraded_mode_manager() -> None:
    """Reset the global DegradedModeManager (for testing)."""
    global _degraded_mode_manager
    _degraded_mode_manager = None

