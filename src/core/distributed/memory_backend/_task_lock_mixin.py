"""
Memory Backend — Task Queue and Lock Operations Mixin.

Contains task queue operations (enqueue, dequeue, complete, fail,
renew_lease, expire_leases) and distributed lock operations.
"""

import copy
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskLockMixin:
    """Mixin providing task queue and distributed lock operations for MemoryBackend."""

    # ----------------------------------------------------------
    #  TASK QUEUE
    # ----------------------------------------------------------

    async def enqueue_task(
        self,
        queue_name: str,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        delay_until: Optional[float] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        with self._lock:
            if task_id in self._task_index:
                logger.warning("MemoryBackend: Task %s already exists", task_id)
                return False

            task = {
                "task_id": task_id,
                "queue_name": queue_name,
                "task_type": task_type,
                "payload": payload,
                "priority": priority,
                "delay_until": delay_until,
                "tenant_id": tenant_id,
                "status": "pending",
                "worker_id": None,
                "lease_expires_at": None,
                "created_at": time.time(),
                "completed_at": None,
                "result": None,
                "error": None,
                "retry_count": 0,
                "max_retries": 3,
            }
            self._tasks[queue_name].append(task)
            self._task_index[task_id] = task
            logger.debug(
                "MemoryBackend: Enqueued task %s in queue '%s'",
                task_id[:8], queue_name,
            )
            return True

    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        lease_seconds: float = 120.0,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            available = []
            for task in self._tasks.get(queue_name, []):
                if task["status"] != "pending":
                    continue
                if task["delay_until"] and task["delay_until"] > now:
                    continue
                if task_types and task["task_type"] not in task_types:
                    continue
                if tenant_id and task.get("tenant_id") != tenant_id:
                    continue
                available.append(task)

            if not available:
                return None

            available.sort(key=lambda t: (-t["priority"], t["created_at"]))
            task = available[0]

            task["status"] = "running"
            task["worker_id"] = worker_id
            task["lease_expires_at"] = now + lease_seconds

            return copy.deepcopy(task)

    async def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if task is None:
                return False
            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["result"] = result
            task["lease_expires_at"] = None
            return True

    async def fail_task(self, task_id: str, error: str, retryable: bool = True) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if task is None:
                return False

            if retryable and task["retry_count"] < task["max_retries"]:
                task["status"] = "pending"
                task["retry_count"] += 1
                task["worker_id"] = None
                task["lease_expires_at"] = None
                task["error"] = error
                logger.info(
                    "MemoryBackend: Task %s failed (retry %d/%d): %s",
                    task_id[:8], task["retry_count"], task["max_retries"], error,
                )
            else:
                task["status"] = "failed"
                task["completed_at"] = time.time()
                task["error"] = error
                task["lease_expires_at"] = None
                logger.warning(
                    "MemoryBackend: Task %s permanently failed: %s",
                    task_id[:8], error,
                )
            return True

    async def renew_lease(self, task_id: str, additional_seconds: float = 60.0) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if task is None or task["status"] != "running":
                return False
            task["lease_expires_at"] = time.time() + additional_seconds
            return True

    async def expire_leases(self, queue_name: str) -> int:
        now = time.time()
        expired_count = 0
        with self._lock:
            for task in self._tasks.get(queue_name, []):
                if (
                    task["status"] == "running"
                    and task["lease_expires_at"]
                    and task["lease_expires_at"] < now
                ):
                    task["status"] = "pending"
                    task["worker_id"] = None
                    task["lease_expires_at"] = None
                    expired_count += 1
                    logger.info(
                        "MemoryBackend: Expired lease for task %s",
                        task["task_id"][:8],
                    )
        return expired_count

    # ----------------------------------------------------------
    #  DISTRIBUTED LOCKS
    # ----------------------------------------------------------

    async def acquire_lock(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float = 60.0,
        timeout_seconds: float = 0.0,
    ) -> bool:
        deadline = time.time() + timeout_seconds
        while True:
            with self._lock:
                lock = self._locks.get(lock_name)
                now = time.time()

                if lock is None or lock["expires_at"] < now:
                    self._locks[lock_name] = {
                        "holder_id": holder_id,
                        "expires_at": now + ttl_seconds,
                        "acquired_at": now,
                    }
                    return True

                if lock["holder_id"] == holder_id:
                    lock["expires_at"] = now + ttl_seconds
                    return True

            if now >= deadline:
                return False

            time.sleep(min(0.1, deadline - now))

    async def release_lock(self, lock_name: str, holder_id: str) -> bool:
        with self._lock:
            lock = self._locks.get(lock_name)
            if lock is None:
                return False
            if lock["holder_id"] != holder_id:
                return False
            del self._locks[lock_name]
            return True

    async def extend_lock(self, lock_name: str, holder_id: str, additional_seconds: float = 30.0) -> bool:
        with self._lock:
            lock = self._locks.get(lock_name)
            if lock is None or lock["holder_id"] != holder_id:
                return False
            lock["expires_at"] = time.time() + additional_seconds
            return True

    async def is_locked(self, lock_name: str) -> bool:
        with self._lock:
            lock = self._locks.get(lock_name)
            if lock is None:
                return False
            if lock["expires_at"] < time.time():
                del self._locks[lock_name]
                return False
            return True
