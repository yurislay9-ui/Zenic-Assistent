"""Re-exports for engine package."""

from ._types import *
from ._mixin_core import *

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

_engine_instance: Optional[RiskPredictionEngine] = None
_engine_lock = threading.Lock()
def get_risk_prediction_engine() -> RiskPredictionEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = RiskPredictionEngine()
        return _engine_instance


def reset_risk_prediction_engine() -> None:
    global _engine_instance
    with _engine_lock:
        _engine_instance = None

