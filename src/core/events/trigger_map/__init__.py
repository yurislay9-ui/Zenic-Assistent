"""Re-exports for trigger_map package."""

from ._types import *
from ._helpers import *
from ._mixin_core import *

import fnmatch
import json
import logging
import os
import sqlite3
import threading
import time
import uuid

_instance: TriggerMap | None = None
_instance_lock = threading.Lock()
def get_trigger_map() -> TriggerMap:
    """Return the singleton TriggerMap instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TriggerMap()
    return _instance


def reset_trigger_map() -> None:
    """Reset the singleton (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None



__all__ = [
    "TriggerMap",
    "TriggerMapping",
    "TriggerCondition",
    "ConditionOperator",
    "get_trigger_map",
    "reset_trigger_map",
]