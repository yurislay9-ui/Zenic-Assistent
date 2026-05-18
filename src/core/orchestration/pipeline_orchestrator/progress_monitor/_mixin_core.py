"""Core logic for progress_monitor."""

from __future__ import annotations
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from ._types import *

logger = logging.getLogger(__name__)

class _PipelineProgress:
    """Internal pipeline progress tracker."""

    __slots__ = (
        "pipeline_id", "total_steps", "completed_steps",
        "failed_steps", "skipped_steps", "current_step",
        "step_states", "step_weights", "started_at",
        "finished_at", "status",
    )

    def __init__(
        self,
        pipeline_id: str,
        total_steps: int = 0,
        step_weights: Optional[Dict[str, float]] = None,
        started_at: Optional[float] = None,
    ) -> None:
        self.pipeline_id = pipeline_id
        self.total_steps = total_steps
        self.completed_steps = 0
        self.failed_steps = 0
        self.skipped_steps = 0
        self.current_step = ""
        self.step_states: Dict[str, _StepProgress] = {}
        self.step_weights = step_weights or {}
        self.started_at = started_at
        self.finished_at: Optional[float] = None
        self.status = ProgressStatus.RUNNING

