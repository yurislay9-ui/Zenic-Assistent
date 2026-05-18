"""Helpers for experiment_runner."""

from __future__ import annotations
import logging
import time
from typing import Any

logger = logging.getLogger("zenic_agents.core.chaos.experiment_runner")

def _retry(func: Any, max_retries: int = 3, base_delay: float = 1.0) -> Any:
    for attempt in range(max_retries):
        try:
            return func()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
