"""Re-exports for inter_workflow package."""

from ._types import *
from ._helpers import *
from ._mixin_core import *

import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid

_instance: InterWorkflowHandoff | None = None
_instance_lock = threading.Lock()
def get_inter_workflow_handoff() -> InterWorkflowHandoff:
    """Return the InterWorkflowHandoff singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = InterWorkflowHandoff()
    return _instance



__all__ = [
    "HandoffRule",
    "HandoffResult",
    "FieldMapping",
    "InterWorkflowHandoff",
    "get_inter_workflow_handoff",
]