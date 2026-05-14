"""
ZENIC-AGENTS - Distributed Task Queue: Core Mixin

Enqueue, dequeue, and lifecycle methods for DistributedTaskQueue.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

from ._types import TaskMessage

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing core queue operations for DistributedTaskQueue."""

    # Default queue depth limit for back-pressure
    DEFAULT_MAX_QUEUE_DEPTH = 10000

    async def connect(self: Any) -> None:
        """Initialize the queue by connecting the backend."""
        await self._backend.connect()
        logger.info(
            "DistributedTaskQueue: Connected (backend=%s)",
            type(self._backend).__name__,
        )

    async def disconnect(self: Any) -> None:
        """Disconnect the queue backend."""
        await self._backend.disconnect()
        logger.info("DistributedTaskQueue: Disconnected")

    async def enqueue(self: Any, message: TaskMessage) -> str:
        """
        Add a task to the queue.

        Args:
            message: TaskMessage describing the task.

        Returns:
            The task_id of the enqueued task.

        Raises:
            ValueError: If the queue is at capacity.
        """
        success = await self._backend.enqueue_task(
            queue_name=message.queue_name,
            task_id=message.task_id,
            task_type=message.task_type,
            payload=message.payload,
            priority=message.priority,
            delay_until=message.delay_until,
            tenant_id=message.tenant_id,
        )

        if not success:
            raise ValueError(
                f"Failed to enqueue task {message.task_id} "
                f"(queue={message.queue_name})"
            )

        with self._stats_lock:
            self._total_enqueued += 1

        logger.info(
            "TaskQueue: Enqueued %s (queue=%s, type=%s, priority=%d)",
            message.task_id[:8], message.queue_name,
            message.task_type, message.priority,
        )
        return message.task_id

    async def enqueue_batch(self: Any, messages: List[TaskMessage]) -> List[str]:
        """
        Enqueue multiple tasks.

        Args:
            messages: List of TaskMessage instances.

        Returns:
            List of task_ids for successfully enqueued tasks.
        """
        task_ids: List[str] = []
        for msg in messages:
            try:
                tid = await self.enqueue(msg)
                task_ids.append(tid)
            except Exception as exc:
                logger.error(
                    "TaskQueue: Batch enqueue failed for %s: %s",
                    msg.task_id[:8], exc,
                )
        return task_ids

    async def dequeue(
        self: Any,
        queue_name: str,
        worker_id: str,
        lease_seconds: Optional[float] = None,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Claim the highest-priority available task.

        Args:
            queue_name: Queue to dequeue from.
            worker_id: ID of the claiming worker.
            lease_seconds: Task lease duration (default from config).
            task_types: Filter by task type.
            tenant_id: Filter by tenant.

        Returns:
            Task dict, or None if no task available.
        """
        lease = lease_seconds or self._default_lease_seconds

        task = await self._backend.dequeue_task(
            queue_name=queue_name,
            worker_id=worker_id,
            lease_seconds=lease,
            task_types=task_types,
            tenant_id=tenant_id,
        )

        if task is not None:
            with self._stats_lock:
                self._total_dequeued += 1
            logger.debug(
                "TaskQueue: Dequeued %s by worker %s",
                task.get("task_id", "")[:8], worker_id,
            )

        return task
