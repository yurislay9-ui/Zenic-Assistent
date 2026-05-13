"""
ZENIC-AGENTS - Concurrency Pattern: Worker Pool

Dynamic, priority-aware thread pool with configurable scaling.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
The pool dynamically grows/shrinks within [min_workers, max_workers]
based on queue depth and idle time.
"""

import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Configuration
# ======================================================================

@dataclass
class WorkerPoolConfig:
    """
    Configuration for :class:`WorkerPool`.

    Attributes:
        min_workers: Minimum number of persistent worker threads.
        max_workers: Maximum number of worker threads.
        queue_size: Maximum items in the work queue (0 = unbounded).
        idle_timeout: Seconds before an idle excess worker exits.
        name: Human-readable pool name (used in logging & thread names).
    """
    min_workers: int = 2
    max_workers: int = 4
    queue_size: int = 50
    idle_timeout: float = 60.0
    name: str = "default"


# ======================================================================
# Internal work item
# ======================================================================

class _WorkItem:
    """Internal representation of a submitted task."""

    __slots__ = ("fn", "args", "kwargs", "future", "priority", "submit_time", "_sentinel")

    def __init__(
        self,
        fn: Callable[..., Any] = None,
        args: tuple = (),
        kwargs: dict = None,
        future: Future = None,
        priority: int = 0,
        _sentinel: bool = False,
    ) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs if kwargs is not None else {}
        self.future = future
        self.priority = priority
        self.submit_time = time.monotonic()
        self._sentinel = _sentinel

    def __lt__(self, other: "_WorkItem") -> bool:
        """Higher priority = lower number = dequeued first."""
        return self.priority < other.priority


_SENTINEL = _WorkItem(priority=1_000_000, _sentinel=True)


# ======================================================================
# Worker Pool
# ======================================================================

class WorkerPool:
    """
    Thread pool with dynamic scaling and priority scheduling.

    Workers are daemon threads that pull work items from a priority
    queue.  The pool starts with ``min_workers`` threads and grows up
    to ``max_workers`` when the queue is backlogged.  Excess workers
    exit after ``idle_timeout`` seconds of inactivity.

    Usage::

        cfg = WorkerPoolConfig(min_workers=2, max_workers=6)
        pool = WorkerPool(cfg)
        future = pool.submit(time.sleep, 1)
        future.result()   # blocks until done
        pool.shutdown()
    """

    def __init__(self, config: WorkerPoolConfig) -> None:
        self._config = config
        self._work_queue: queue.PriorityQueue[_WorkItem] = queue.PriorityQueue(
            maxsize=config.queue_size if config.queue_size > 0 else 0
        )
        self._workers: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._shutdown = False
        self._active_count = 0
        self._active_lock = threading.Lock()
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0

        # Start minimum workers
        for _ in range(config.min_workers):
            self._add_worker()

        logger.debug(
            "WorkerPool '%s': started with %d workers",
            config.name, config.min_workers,
        )

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Future:
        """
        Submit a callable for execution.

        Args:
            fn: The callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            A :class:`~concurrent.futures.Future` representing the result.

        Raises:
            RuntimeError: If the pool has been shut down.
            queue.Full: If the queue is at capacity.
        """
        return self._do_submit(fn, 0, args, kwargs)

    def submit_with_priority(
        self,
        fn: Callable[..., Any],
        priority: int = 0,
        *args: Any,
        **kwargs: Any,
    ) -> Future:
        """
        Submit a callable with a priority (lower = higher priority).

        Args:
            fn: The callable to execute.
            priority: Scheduling priority (default 0).
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            A :class:`~concurrent.futures.Future`.

        Raises:
            RuntimeError: If the pool has been shut down.
        """
        return self._do_submit(fn, priority, args, kwargs)

    def _do_submit(
        self,
        fn: Callable[..., Any],
        priority: int,
        args: tuple,
        kwargs: dict,
    ) -> Future:
        """Internal submit implementation."""
        if self._shutdown:
            raise RuntimeError("WorkerPool: cannot submit after shutdown")

        future: Future = Future()
        item = _WorkItem(fn, args, kwargs, future, priority)

        # Try to grow the pool if the queue is backing up
        with self._lock:
            qsize = self._work_queue.qsize()
            worker_count = len(self._workers)

        if qsize > 0 and worker_count < self._config.max_workers:
            self._add_worker()

        self._work_queue.put(item, block=True, timeout=5.0)

        with self._active_lock:
            self._total_submitted += 1

        return future

    def map(
        self,
        fn: Callable[..., Any],
        iterables: List[Any],
    ) -> List[Future]:
        """
        Submit *fn* for each item in *iterables*.

        Args:
            fn: Callable that accepts a single argument.
            iterables: List of arguments (one per call).

        Returns:
            List of :class:`~concurrent.futures.Future` objects.
        """
        futures: List[Future] = []
        for item in iterables:
            futures.append(self.submit(fn, item))
        return futures

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, wait: bool = True) -> None:
        """
        Shut down the pool.

        Args:
            wait: If True, block until all submitted work is complete.
        """
        self._shutdown = True
        logger.debug("WorkerPool '%s': shutting down", self._config.name)

        # Signal workers by pushing sentinel items
        for _ in self._workers:
            try:
                self._work_queue.put_nowait(_SENTINEL)
            except queue.Full:
                break

        if wait:
            for w in self._workers:
                w.join(timeout=10.0)

        logger.debug("WorkerPool '%s': shutdown complete", self._config.name)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active_workers(self) -> int:
        """Return the number of currently running worker threads."""
        with self._lock:
            return sum(1 for w in self._workers if w.is_alive())

    @property
    def pending_tasks(self) -> int:
        """Return the number of tasks waiting in the queue."""
        return self._work_queue.qsize()

    @property
    def stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        with self._lock:
            worker_count = len(self._workers)
        return {
            "name": self._config.name,
            "active_workers": self.active_workers,
            "total_workers": worker_count,
            "min_workers": self._config.min_workers,
            "max_workers": self._config.max_workers,
            "pending_tasks": self.pending_tasks,
            "total_submitted": self._total_submitted,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_worker(self) -> None:
        """Start a new worker thread (up to max_workers)."""
        with self._lock:
            if len(self._workers) >= self._config.max_workers:
                return
            idx = len(self._workers)
            t = threading.Thread(
                target=self._worker_loop,
                name=f"{self._config.name}-worker-{idx}",
                daemon=True,
            )
            self._workers.append(t)
        t.start()

    def _worker_loop(self) -> None:
        """Main loop for each worker thread."""
        while not self._shutdown:
            try:
                item = self._work_queue.get(block=True, timeout=self._config.idle_timeout)
            except queue.Empty:
                # Idle timeout — shrink if above min_workers
                with self._lock:
                    if len(self._workers) > self._config.min_workers:
                        # Mark this thread for removal (simply exit)
                        logger.debug("WorkerPool '%s': idle worker exiting", self._config.name)
                        return
                continue

            if isinstance(item, _WorkItem) and item._sentinel:
                # Sentinel — shutdown signal
                break

            with self._active_lock:
                self._active_count += 1

            try:
                result = item.fn(*item.args, **item.kwargs)
                item.future.set_result(result)
                with self._active_lock:
                    self._total_completed += 1
            except Exception as exc:
                item.future.set_exception(exc)
                with self._active_lock:
                    self._total_failed += 1
                logger.error(
                    "WorkerPool '%s': task failed – %s", self._config.name, exc
                )
            finally:
                with self._active_lock:
                    self._active_count -= 1

        # Cleanup dead workers from list periodically
        with self._lock:
            self._workers = [w for w in self._workers if w.is_alive()]
