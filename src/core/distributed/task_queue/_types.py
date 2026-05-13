"""
ZENIC-AGENTS - Distributed Task Queue: Types

TaskStatus, TaskPriority enums and TaskMessage dataclass.
"""

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class TaskStatus(str, enum.Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class TaskPriority(int, enum.Enum):
    """Predefined priority levels."""
    LOW = 10
    NORMAL = 5
    HIGH = 1
    CRITICAL = 0


@dataclass
class TaskMessage:
    """
    Immutable task message for the distributed queue.

    Attributes:
        task_id: Unique task identifier (auto-generated if empty).
        queue_name: Logical queue name for routing.
        task_type: Task type for dispatch routing.
        payload: Task payload (JSON-serializable dict).
        priority: Higher priority = dequeued first (lower number = higher).
        delay_until: Unix timestamp; task not available before this.
        tenant_id: Optional tenant ID for multi-tenant isolation.
        max_retries: Maximum retry attempts on failure.
        created_at: Unix timestamp of creation.
        correlation_id: Optional correlation ID for tracing across tasks.
    """
    task_id: str = ""
    queue_name: str = "default"
    task_type: str = "generic"
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = TaskPriority.NORMAL
    delay_until: Optional[float] = None
    tenant_id: Optional[str] = None
    max_retries: int = 3
    created_at: float = 0.0
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = f"task-{uuid.uuid4().hex[:12]}"
        if self.created_at == 0.0:
            self.created_at = time.time()
