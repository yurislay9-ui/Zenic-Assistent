"""
ZENIC-AGENTS - Distributed Task Queue

Persistent, priority-based task queue backed by the CoordinationBackend.
Supports multi-tenant isolation, delayed tasks, lease-based execution,
and automatic retry with exponential backoff.

Key Features:
    - Priority-based dequeuing (higher priority first)
    - Lease-based task claiming with automatic expiration
    - Delayed task scheduling (delay_until)
    - Multi-tenant task isolation
    - Task type filtering for specialized workers
    - Automatic retry on failure (configurable max_retries)
    - Dead letter queue for permanently failed tasks
    - Back-pressure via queue depth limits
    - Statistics for observability

Designed for PostgreSQL (production) and MemoryBackend (dev/testing).
"""

import logging
import threading
from typing import Any, Optional

from ..backend import BackendConfig, CoordinationBackend
from src.core.patterns.resilience.retry import RetryConfig, with_retry
from ._types import TaskMessage, TaskPriority, TaskStatus
from ._core_mixin import CoreMixin
from ._lifecycle_mixin import LifecycleMixin

logger = logging.getLogger(__name__)

__all__ = [
    "DistributedTaskQueue",
    "TaskMessage",
    "TaskStatus",
    "TaskPriority",
]


class DistributedTaskQueue(CoreMixin, LifecycleMixin):
    """
    Persistent, distributed task queue with priority scheduling.

    Backed by CoordinationBackend (PostgreSQL for production,
    Memory for dev/testing). Supports lease-based task claiming,
    automatic retries, and multi-tenant isolation.

    Usage::

        from src.core.distributed import DistributedTaskQueue, BackendConfig

        queue = DistributedTaskQueue(
            backend=CoordinationBackend.create(BackendConfig()),
        )
        await queue.connect()

        # Enqueue
        msg = TaskMessage(
            queue_name="pipeline",
            task_type="code_generation",
            payload={"description": "Build REST API"},
            priority=TaskPriority.HIGH,
        )
        task_id = await queue.enqueue(msg)

        # Dequeue (for workers)
        task = await queue.dequeue("pipeline", worker_id="worker-1")

        # Complete
        await queue.complete(task["task_id"], result={"files": 5})

        await queue.disconnect()

    Thread Safety:
        The queue itself is thread-safe. Backend operations are
        serialized by the backend's internal locking.
    """

    # Default queue depth limit for back-pressure
    DEFAULT_MAX_QUEUE_DEPTH = 10000

    def __init__(
        self,
        backend: CoordinationBackend,
        max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH,
        default_lease_seconds: float = 120.0,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        """
        Initialize the distributed task queue.

        Args:
            backend: Coordination backend for persistent state.
            max_queue_depth: Maximum pending tasks per queue (back-pressure).
            default_lease_seconds: Default task lease duration.
            retry_config: Retry configuration for backend operations.
        """
        self._backend = backend
        self._max_queue_depth = max_queue_depth
        self._default_lease_seconds = default_lease_seconds
        self._retry_config = retry_config or RetryConfig(
            max_attempts=2,
            base_delay=0.3,
            max_delay=5.0,
            backoff_strategy="exponential",
            jitter=True,
            retryable_exceptions=(Exception,),
        )

        # Stats
        self._total_enqueued: int = 0
        self._total_dequeued: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_retried: int = 0
        self._stats_lock = threading.Lock()
