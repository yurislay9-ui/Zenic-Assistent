"""Re-exports for learning_engine package."""

from ._types import *
from ._helpers import *
from ._mixin_patterns import *
from ._mixin_core import *

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

_instance: Optional[LearningEngine] = None
_instance_lock = threading.Lock()
def get_learning_engine() -> LearningEngine:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LearningEngine()
    return _instance


def reset_learning_engine() -> None:
    global _instance
    with _instance_lock:
        _instance = None

