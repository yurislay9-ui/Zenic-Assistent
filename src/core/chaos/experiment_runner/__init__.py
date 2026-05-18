"""Re-exports for experiment_runner package."""

from ._types import *
from ._helpers import *
from ._mixin_persistence import *
from ._mixin_core import *

import threading
from typing import Optional

_runner_instance: Optional[ChaosExperimentRunner] = None
_runner_lock = threading.Lock()
def get_chaos_runner(db_path: Optional[str] = None) -> ChaosExperimentRunner:
    global _runner_instance
    with _runner_lock:
        if _runner_instance is None:
            _runner_instance = ChaosExperimentRunner(db_path=db_path)
        return _runner_instance


def reset_chaos_runner() -> None:
    global _runner_instance
    with _runner_lock:
        _runner_instance = None
