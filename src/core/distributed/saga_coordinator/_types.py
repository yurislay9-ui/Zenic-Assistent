"""DistributedSagaCoordinator - Types and configuration."""

import enum
from dataclasses import dataclass
from typing import Optional

from ..task_queue import TaskPriority


# ============================================================
#  ENUMS
# ============================================================

class DistributedSagaState(str, enum.Enum):
    """Saga lifecycle states (consistent with single-process SagaStatus)."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


# ============================================================
#  SAGA STEP DEFINITION
# ============================================================

@dataclass
class DistributedSagaStep:
    """
    Definition of a step in a distributed saga.

    Attributes:
        name: Human-readable step name.
        action_task_type: Task type for the step's forward action.
        compensation_task_type: Task type for the step's compensation
                                (None if not compensatable).
        timeout: Optional timeout in seconds.
        priority: Task priority for queue scheduling.
    """
    name: str
    action_task_type: str = ""
    compensation_task_type: Optional[str] = None
    timeout: Optional[float] = None
    priority: int = TaskPriority.NORMAL

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("DistributedSagaStep name must not be empty")
        if not self.action_task_type:
            # Default: use name as task type
            self.action_task_type = f"saga_step_{self.name}"
