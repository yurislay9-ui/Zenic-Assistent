"""Re-exports for engine package."""

from ._types import *
from ._helpers import *
from ._mixin_core import *

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

_engine_instance: Optional[ExceptionEngine] = None
_engine_lock = threading.Lock()
def get_exception_engine(db_path: str = "exception_engine.sqlite") -> ExceptionEngine:
    """Get or create the global :class:`ExceptionEngine` instance."""
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = ExceptionEngine(db_path=db_path)
        return _engine_instance


def reset_exception_engine() -> None:
    """Reset the global :class:`ExceptionEngine` (for testing)."""
    global _engine_instance
    with _engine_lock:
        _engine_instance = None


__all__ = [
    "ExceptionSignal",
    "ExceptionRecord",
    "ExceptionEngine",
    "get_exception_engine",
    "reset_exception_engine",
]