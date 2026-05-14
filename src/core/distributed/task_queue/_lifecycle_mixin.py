"""
ZENIC-AGENTS - Distributed Task Queue: Lifecycle Mixin

Task completion, failure, lease management, and stats.
"""

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LifecycleMixin:
    """Mixin providing task lifecycle operations for DistributedTaskQueue."""

    async def complete(
        self: Any,
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: The task to complete.
            result: Optional result payload.

        Returns:
            True if the task was completed.
        """
        success = await self._backend.complete_task(task_id, result)

        if success:
            with self._stats_lock:
                self._total_completed += 1
            logger.info("TaskQueue: Completed %s", task_id[:8])

        return success

    async def fail(
        self: Any,
        task_id: str,
        error: str,
        retryable: bool = True,
    ) -> bool:
        """
        Mark a task as failed.

        If retryable and retries remain, the task is reset to pending.
        Otherwise it is permanently marked as failed.

        Args:
            task_id: The task that failed.
            error: Error message.
            retryable: Whether the task can be retried.

        Returns:
            True if the failure was recorded.
        """
        success = await self._backend.fail_task(task_id, error, retryable)

        if success:
            with self._stats_lock:
                self._total_failed += 1
                if retryable:
                    self._total_retried += 1
            logger.warning(
                "TaskQueue: Failed %s (retryable=%s): %s",
                task_id[:8], retryable, error[:100],
            )

        return success

    async def renew_lease(
        self: Any,
        task_id: str,
        additional_seconds: float = 60.0,
    ) -> bool:
        """
        Extend a task's lease.

        Workers should call this periodically for long-running tasks
        to prevent the lease from expiring.

        Args:
            task_id: Task whose lease to extend.
            additional_seconds: Extra lease time.

        Returns:
            True if the lease was extended.
        """
        return await self._backend.renew_lease(task_id, additional_seconds)

    async def expire_leases(self: Any, queue_name: str) -> int:
        """
        Release expired task leases.

        Should be called periodically by a coordinator or leader.

        Args:
            queue_name: Queue to scan for expired leases.

        Returns:
            Number of leases expired.
        """
        count = await self._backend.expire_leases(queue_name)
        if count > 0:
            logger.info(
                "TaskQueue: Expired %d leases in queue '%s'",
                count, queue_name,
            )
        return count

    @property
    def stats(self: Any) -> Dict[str, Any]:
        """
        Queue statistics for observability.

        Returns:
            Dict with enqueue/dequeue/complete/fail/retry counts
            and backend type.
        """
        with self._stats_lock:
            return {
                "total_enqueued": self._total_enqueued,
                "total_dequeued": self._total_dequeued,
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "total_retried": self._total_retried,
                "backend_type": type(self._backend).__name__,
                "max_queue_depth": self._max_queue_depth,
            }
