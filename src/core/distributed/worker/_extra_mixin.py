"""DistributedWorker - Additional methods."""

import asyncio
import logging
import socket
import platform
import time
from typing import Any, Dict, Optional

from ._types import WorkerState
from ._helpers import _run_async, _METRICS_AVAILABLE, get_metrics_collector

logger = logging.getLogger("zenic_agents.distributed.worker")


class DistributedWorkerExtraMixin:
    """Additional methods."""

    def current_task(self) -> Optional[Dict[str, Any]]:
        """Currently executing task, if any."""
        return self._current_task
    def stats(self) -> Dict[str, Any]:
        """Worker statistics."""
        with self._lock:
            return {
                "worker_id": self._config.worker_id,
                "state": self._state.value,
                "tasks_completed": self._tasks_completed,
                "tasks_failed": self._tasks_failed,
                "tasks_stolen": self._tasks_stolen,
                "current_task": (
                    self._current_task.get("task_id", "")[:8]
                    if self._current_task else None
                ),
                "registered_handlers": list(self._handlers.keys()),
                "queue_names": self._config.queue_names,
                "uptime_s": (
                    time.time() - self._start_time
                    if hasattr(self, "_start_time") else 0
                ),
            }
    def _main_loop(self) -> None:
        """Main worker loop: poll for tasks and execute them."""
        self._start_time = time.time()

        while not self._stop_event.is_set():
            if self._state in (WorkerState.PAUSED, WorkerState.STOPPING):
                self._stop_event.wait(timeout=1.0)
                continue

            # Try each configured queue (H-07: reuse thread-local loop)
            task = None
            for queue_name in self._config.queue_names:
                try:
                    task = _run_async(
                        self._queue.dequeue(
                            queue_name=queue_name,
                            worker_id=self._config.worker_id,
                            lease_seconds=self._config.lease_seconds,
                            task_types=self._config.task_types,
                            tenant_id=self._config.tenant_id,
                        )
                    )
                except Exception as exc:
                    logger.error(
                        "Worker %s: Dequeue error from '%s': %s",
                        self._config.worker_id, queue_name, exc,
                    )

                if task is not None:
                    break

            if task is None:
                self._state = WorkerState.IDLE
                self._stop_event.wait(timeout=self._config.poll_interval)
                continue

            # Execute the task
            self._state = WorkerState.RUNNING
            self._execute_task(task)

        self._state = WorkerState.STOPPED
    def _execute_task(self, task: Dict[str, Any]) -> None:
        """
        Execute a single task with the appropriate handler.

        Handles:
        - Handler lookup
        - Lease renewal for long-running tasks
        - Result reporting (complete/fail)
        - Error isolation
        """
        task_id = task.get("task_id", "unknown")
        task_type = task.get("task_type", "unknown")

        self._current_task = task
        self._task_start_time = time.time()

        handler = self._handlers.get(task_type)

        if handler is None:
            logger.error(
                "Worker %s: No handler for task type '%s' (task=%s)",
                self._config.worker_id, task_type, task_id[:8],
            )
            self._report_failure(task_id, f"No handler registered for task type '{task_type}'")
            self._current_task = None
            return

        logger.info(
            "Worker %s: Executing task %s (type=%s)",
            self._config.worker_id, task_id[:8], task_type,
        )

        try:
            result = handler(task)

            # If handler returns a coroutine, run it on the thread-local loop
            if asyncio.iscoroutine(result):
                result = _run_async(result)

            # Report success
            self._report_success(task_id, result)

        except Exception as exc:
            logger.error(
                "Worker %s: Task %s failed: %s",
                self._config.worker_id, task_id[:8], exc,
                exc_info=True,
            )
            self._report_failure(task_id, str(exc))

        finally:
            self._current_task = None
            self._task_start_time = 0.0
    def _report_success(self, task_id: str, result: Any) -> None:
        """Report a completed task."""
        result_dict = None
        if isinstance(result, dict):
            result_dict = result
        elif result is not None:
            result_dict = {"value": result}

        try:
            _run_async(self._queue.complete(task_id, result_dict))
        except Exception as exc:
            logger.error(
                "Worker %s: Failed to report completion for %s: %s",
                self._config.worker_id, task_id[:8], exc,
            )
        else:
            with self._lock:
                self._tasks_completed += 1
                # Phase 5: Emit metrics
                if _METRICS_AVAILABLE:
                    try:
                        mc = get_metrics_collector()
                        mc.record_task_completed(
                            task_type=self._current_task.get("task_type", "unknown") if self._current_task else "unknown",
                            worker_id=self._config.worker_id,
                            duration=time.time() - self._task_start_time if self._task_start_time else 0.0,
                        )
                    except Exception:
                        pass
    def _report_failure(self, task_id: str, error: str) -> None:
        """Report a failed task."""
        try:
            _run_async(self._queue.fail(task_id, error, retryable=True))
        except Exception as exc:
            logger.error(
                "Worker %s: Failed to report failure for %s: %s",
                self._config.worker_id, task_id[:8], exc,
            )
        else:
            with self._lock:
                self._tasks_failed += 1
                # Phase 5: Emit metrics
                if _METRICS_AVAILABLE:
                    try:
                        mc = get_metrics_collector()
                        mc.record_task_failed(
                            task_type=self._current_task.get("task_type", "unknown") if self._current_task else "unknown",
                            worker_id=self._config.worker_id,
                        )
                    except Exception:
                        pass
    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to the cluster topology."""
        while not self._stop_event.is_set():
            try:
                status = {
                    "state": self._state.value,
                    "tasks_completed": self._tasks_completed,
                    "tasks_failed": self._tasks_failed,
                    "current_task_type": (
                        self._current_task.get("task_type")
                        if self._current_task else None
                    ),
                }
                _run_async(
                    self._backend.heartbeat(
                        self._config.worker_id, status
                    )
                )
            except Exception as exc:
                logger.debug(
                    "Worker %s: Heartbeat error: %s",
                    self._config.worker_id, exc,
                )

            self._stop_event.wait(timeout=self._config.heartbeat_interval)
    def _lease_renewal_loop(self) -> None:
        """Renew task leases for long-running operations."""
        while not self._stop_event.is_set():
            if self._current_task is not None:
                task_id = self._current_task.get("task_id", "")
                try:
                    _run_async(
                        self._queue.renew_lease(
                            task_id,
                            self._config.lease_seconds * 0.5,
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "Worker %s: Lease renewal failed for %s: %s",
                        self._config.worker_id, task_id[:8], exc,
                    )

            self._stop_event.wait(
                timeout=self._config.lease_renewal_interval
            )
    def _register_in_topology(self) -> None:
        """Register this worker in the cluster topology."""
        try:
            _run_async(
                self._backend.register_node({
                    "node_id": self._config.worker_id,
                    "hostname": socket.gethostname(),
                    "ip_address": self._get_local_ip(),
                    "capabilities": {
                        "task_types": list(self._handlers.keys()),
                        "queue_names": self._config.queue_names,
                        "max_concurrent": self._config.max_concurrent_tasks,
                        "platform": platform.platform(),
                    },
                })
            )
        except Exception as exc:
            logger.warning(
                "Worker %s: Topology registration failed: %s",
                self._config.worker_id, exc,
            )
    def _deregister_from_topology(self) -> None:
        """Remove this worker from the cluster topology."""
        try:
            _run_async(
                self._backend.deregister_node(self._config.worker_id)
            )
        except Exception as exc:
            logger.warning(
                "Worker %s: Topology deregistration failed: %s",
                self._config.worker_id, exc,
            )
    def _get_local_ip() -> str:
        """Get the local IP address (best effort)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
