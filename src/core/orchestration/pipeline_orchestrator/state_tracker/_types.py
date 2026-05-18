"""Types and constants for state_tracker."""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class PipelineStatus(str, Enum):
    """Overall pipeline status."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"



class StepExecutionStatus(str, Enum):
    """Status of an individual step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"



@dataclass
class StepState:
    """
    State of an individual pipeline step.

    Attributes:
        step_id: Unique identifier for the step.
        name: Human-readable name.
        status: Current execution status.
        input_data: Input data for the step.
        output_data: Output data from the step.
        error: Error message if the step failed.
        started_at: Timestamp when execution started.
        completed_at: Timestamp when execution completed.
        duration_ms: Execution duration in milliseconds.
        attempts: Number of execution attempts.
        metadata: Additional metadata.
    """
    step_id: str
    name: str = ""
    status: StepExecutionStatus = StepExecutionStatus.PENDING
    input_data: Any = None
    output_data: Any = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.step_id



@dataclass
class PipelineState:
    """
    State of the entire pipeline.

    Attributes:
        pipeline_id: Unique identifier for the pipeline run.
        name: Human-readable pipeline name.
        status: Overall pipeline status.
        steps: Mapping of step IDs to their state.
        created_at: Timestamp when the pipeline was created.
        started_at: Timestamp when execution started.
        completed_at: Timestamp when execution completed.
        metadata: Additional pipeline-level metadata.
    """
    pipeline_id: str = ""
    name: str = ""
    status: PipelineStatus = PipelineStatus.CREATED
    steps: Dict[str, StepState] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pipeline_id:
            self.pipeline_id = f"pipe-{uuid.uuid4().hex[:8]}"

    @property
    def duration_ms(self) -> float:
        """Total pipeline duration in milliseconds."""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    @property
    def progress_pct(self) -> float:
        """Pipeline progress as a percentage (0-100)."""
        if not self.steps:
            return 0.0
        completed = sum(
            1 for s in self.steps.values()
            if s.status in (StepExecutionStatus.COMPLETED, StepExecutionStatus.SKIPPED)
        )
        return (completed / len(self.steps)) * 100

    @property
    def failed_steps(self) -> List[str]:
        """List of step IDs that have failed."""
        return [
            sid for sid, s in self.steps.items()
            if s.status == StepExecutionStatus.FAILED
        ]

    @property
    def completed_steps(self) -> List[str]:
        """List of step IDs that have completed successfully."""
        return [
            sid for sid, s in self.steps.items()
            if s.status == StepExecutionStatus.COMPLETED
        ]
