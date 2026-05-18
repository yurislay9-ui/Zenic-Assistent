"""Re-exports for conditional_branch package."""

from ._types import *
from ._helpers import *
from ._mixin_core import *

import logging
import re
import threading
import time
import uuid

_instance: ConditionalBranching | None = None
_instance_lock = threading.Lock()
def get_conditional_branching() -> ConditionalBranching:
    """Return the ConditionalBranching singleton (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConditionalBranching()
    return _instance



__all__ = [
    "BranchRule",
    "BranchCondition",
    "ConditionalBranching",
    "safe_evaluate",
    "get_conditional_branching",
]