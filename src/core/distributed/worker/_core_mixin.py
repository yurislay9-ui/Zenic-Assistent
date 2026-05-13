"""DistributedWorker - Core methods."""

import logging
import threading
from typing import Any, Dict, Optional

from ._types import WorkerState, WorkerConfig, TaskHandler
from ._helpers import _local
from ..backend import CoordinationBackend
from ..task_queue import DistributedTaskQueue

logger = logging.getLogger("zenic_agents.distributed.worker")


class DistributedWorkerCoreMixin:
    """Core methods."""

    def __init__(
        self,
        config: WorkerConfig,
        queue: DistributedTaskQueue,
        backend: CoordinationBackend,
    ) -> None:
        self._config = config
        self._queue = queue
        self._backend = backend

        self._state: WorkerState = WorkerState.STOPPED
        self._handlers: Dict[str, TaskHandler] = {}
        self._current_task: Optional[Dict[str, Any]] = None
        self._task_start_time: float = 0.0

        # Background threads
        self._main_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lease_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stats
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._tasks_stolen: int = 0
        self._lock = threading.Lock()
    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        """
        Register a handler for a specific task type.

        Args:
            task_type: The task type this handler processes.
            handler: Callable that receives the task dict and returns a result.
        """
        self._handlers[task_type] = handler
        logger.debug(
            "Worker %s: Registered handler for task type '%s'",
            self._config.worker_id, task_type,
        )
    def register_handlers(self, handlers: Dict[str, TaskHandler]) -> None:
        """
        Register multiple task handlers.

        Args:
            handlers: Dict mapping task_type -> handler callable.
        """
        for task_type, handler in handlers.items():
            self.register_handler(task_type, handler)
    def start(self, blocking: bool = True) -> None:
        """
        Start the worker.

        Args:
            blocking: If True, block until the worker stops.
                     If False, run in background threads.
        """
        if self._state == WorkerState.RUNNING:
            logger.warning("Worker %s: Already running", self._config.worker_id)
            return

        self._state = WorkerState.IDLE
        self._stop_event.clear()

        # Register in topology
        self._register_in_topology()

        # Start background threads
        self._main_thread = threading.Thread(
            target=self._main_loop,
            name=f"worker-{self._config.worker_id}-main",
            daemon=True,
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"worker-{self._config.worker_id}-heartbeat",
            daemon=True,
        )
        self._lease_thread = threading.Thread(
            target=self._lease_renewal_loop,
            name=f"worker-{self._config.worker_id}-lease",
            daemon=True,
        )

        self._main_thread.start()
        self._heartbeat_thread.start()
        self._lease_thread.start()

        logger.info(
            "Worker %s: Started (queues=%s, types=%s)",
            self._config.worker_id,
            self._config.queue_names,
            self._config.task_types or "all",
        )

        if blocking:
            self._main_thread.join()
    async def start_async(self) -> None:
        """Async version of start() — runs worker in background."""
        self.start(blocking=False)
    def stop(self) -> None:
        """
        Signal the worker to stop gracefully.

        Waits up to graceful_shutdown_timeout for current task
        to complete, then forces stop.
        """
        if self._state in (WorkerState.STOPPED, WorkerState.STOPPING):
            return

        self._state = WorkerState.STOPPING
        self._stop_event.set()
        logger.info(
            "Worker %s: Stopping (timeout=%ds)",
            self._config.worker_id,
            self._config.graceful_shutdown_timeout,
        )

        # Wait for main thread
        if self._main_thread and self._main_thread.is_alive():
            self._main_thread.join(timeout=self._config.graceful_shutdown_timeout)

        # Deregister from topology
        self._deregister_from_topology()

        # Close the thread-local event loop (H-07: cleanup)
        loop = getattr(_local, "event_loop", None)
        if loop is not None and not loop.is_closed():
            loop.close()
            _local.event_loop = None

        self._state = WorkerState.STOPPED
        logger.info("Worker %s: Stopped", self._config.worker_id)
    def pause(self) -> None:
        """Pause task processing (heartbeat continues)."""
        self._state = WorkerState.PAUSED
        logger.info("Worker %s: Paused", self._config.worker_id)
    def resume(self) -> None:
        """Resume task processing."""
        self._state = WorkerState.IDLE
        logger.info("Worker %s: Resumed", self._config.worker_id)
    def worker_id(self) -> str:
        """Worker identifier."""
        return self._config.worker_id
    def state(self) -> WorkerState:
        """Current worker state."""
        return self._state
