"""Re-exports for engine package."""

from ._types import *
from ._helpers import *
from ._mixin_persistence import *
from ._mixin_core import *

import threading
from typing import Optional

_engine_instance: Optional[PolicyCodeEngine] = None
_engine_lock = threading.Lock()
def get_policy_code_engine(db_path: Optional[str] = None) -> PolicyCodeEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = PolicyCodeEngine(db_path=db_path)
        return _engine_instance


def reset_policy_code_engine() -> None:
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
