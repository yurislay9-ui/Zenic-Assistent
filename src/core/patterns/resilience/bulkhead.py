"""
ZENIC-AGENTS - Bulkhead Pattern v16

Thread-pool isolation with semaphore-based concurrency limiting and
queue back-pressure. Designed for Android/Termux (500MB RAM) — stdlib only.

Usage::

    bulkhead = Bulkhead("api-pool", max_concurrent=5, max_queue=20)

    with bulkhead.acquire():
        # at most 5 threads execute concurrently
        result = call_external_service()

    # async variant
    async with bulkhead.acquire_async():
        result = await call_async_service()
"""

import asyncio
import threading
import time
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["Bulkhead", "BulkheadFullError"]


# ============================================================
#  EXCEPTIONS
# ============================================================

class BulkheadFullError(Exception):
    """Raised when the bulkhead cannot accept more work within the timeout."""

    def __init__(self, name: str, active: int, max_concurrent: int, queue_size: int):
        self.bulkhead_name = name
        self.active = active
        self.max_concurrent = max_concurrent
        self.queue_size = queue_size
        super().__init__(
            f"Bulkhead '{name}' is full: "
            f"active={active}/{max_concurrent}, queue={queue_size}"
        )


# ============================================================
#  BULKHEAD
# ============================================================

class Bulkhead:
    """
    Thread-safe bulkhead limiting concurrent execution with queue back-pressure.

    Parameters:
        name: Human-readable identifier for this bulkhead.
        max_concurrent: Maximum number of concurrent executions.
        max_queue: Maximum number of waiting requests in the queue.
        timeout: Seconds to wait for a slot before raising BulkheadFullError.
    """

    def __init__(
        self,
        name: str,
        max_concurrent: int = 4,
        max_queue: int = 20,
        timeout: float = 30.0,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if max_queue < 0:
            raise ValueError("max_queue must be >= 0")
        if timeout < 0:
            raise ValueError("timeout must be >= 0")

        self._name = name
        self._max_concurrent = max_concurrent
        self._max_queue = max_queue
        self._timeout = timeout

        # Core synchronization
        self._semaphore = threading.Semaphore(max_concurrent)
        self._condition = threading.Condition(threading.Lock())

        # Counters
        self._active_count = 0
        self._queue_size = 0
        self._total_accepted = 0
        self._total_rejected = 0
        self._total_completed = 0
        self._total_errors = 0

        self._lock = threading.Lock()

    # ----------------------------------------------------------
    #  Properties
    # ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Identifier for this bulkhead."""
        return self._name

    @property
    def active_count(self) -> int:
        """Number of currently active (executing) calls."""
        with self._lock:
            return self._active_count

    @property
    def queue_size(self) -> int:
        """Number of calls currently waiting in the queue."""
        with self._lock:
            return self._queue_size

    @property
    def available(self) -> int:
        """Number of available concurrent slots."""
        with self._lock:
            return self._max_concurrent - self._active_count

    @property
    def stats(self) -> Dict[str, Any]:
        """Snapshot of bulkhead statistics."""
        with self._lock:
            return {
                "name": self._name,
                "max_concurrent": self._max_concurrent,
                "max_queue": self._max_queue,
                "timeout": self._timeout,
                "active_count": self._active_count,
                "queue_size": self._queue_size,
                "available": self._max_concurrent - self._active_count,
                "total_accepted": self._total_accepted,
                "total_rejected": self._total_rejected,
                "total_completed": self._total_completed,
                "total_errors": self._total_errors,
            }

    # ----------------------------------------------------------
    #  Acquire / Release — synchronous
    # ----------------------------------------------------------

    @contextmanager
    def acquire(self):  # noqa: ANN201
        """
        Context manager that acquires a bulkhead slot, blocking until
        one is available or the timeout expires.

        Raises:
            BulkheadFullError: If no slot becomes available within timeout.
        """
        acquired = self._try_enter()
        if not acquired:
            raise BulkheadFullError(
                self._name,
                active=self._active_count,
                max_concurrent=self._max_concurrent,
                queue_size=self._queue_size,
            )
        try:
            yield
        except Exception:
            with self._lock:
                self._total_errors += 1
            raise
        finally:
            self._exit()

    def _try_enter(self) -> bool:
        """
        Attempt to enter the bulkhead within the configured timeout.

        Returns True if a slot was acquired, False otherwise.
        """
        deadline = time.monotonic() + self._timeout

        # Fast path: try the semaphore immediately
        if self._semaphore.acquire(blocking=False):
            with self._lock:
                self._active_count += 1
                self._total_accepted += 1
            return True

        # If queuing is disabled, fail immediately
        if self._max_queue == 0:
            with self._lock:
                self._total_rejected += 1
            return False

        # Enqueue and wait for semaphore
        with self._lock:
            if self._queue_size >= self._max_queue:
                self._total_rejected += 1
                logger.warning(
                    "Bulkhead '%s': queue full (%d/%d), rejecting",
                    self._name, self._queue_size, self._max_queue,
                )
                return False
            self._queue_size += 1
            self._total_accepted += 1

        # Wait for semaphore with remaining timeout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            with self._lock:
                self._queue_size -= 1
                self._total_rejected += 1
            return False

        acquired = self._semaphore.acquire(blocking=True, timeout=remaining)
        with self._lock:
            self._queue_size -= 1
            if acquired:
                self._active_count += 1
            else:
                self._total_rejected += 1
                logger.warning(
                    "Bulkhead '%s': timeout waiting for slot after %.1fs",
                    self._name, self._timeout,
                )
        return acquired

    def _exit(self) -> None:
        """Release a bulkhead slot."""
        self._semaphore.release()
        with self._lock:
            self._active_count -= 1
            self._total_completed += 1

        # Notify any waiting threads
        with self._condition:
            self._condition.notify()

    # ----------------------------------------------------------
    #  Acquire / Release — async
    # ----------------------------------------------------------

    @asynccontextmanager
    async def acquire_async(self):  # noqa: ANN201
        """
        Async context manager that acquires a bulkhead slot.

        Uses an ``asyncio.Semaphore`` for non-blocking concurrency
        control with timeout support and queue back-pressure tracking.
        """
        if not hasattr(self, "_async_semaphore"):
            self._async_semaphore = asyncio.Semaphore(self._max_concurrent)

        # Quick rejection: queue is already full and no slots free
        with self._lock:
            if (
                self._max_queue >= 0
                and self._active_count >= self._max_concurrent
                and self._queue_size >= self._max_queue
            ):
                self._total_rejected += 1
                raise BulkheadFullError(
                    self._name,
                    active=self._active_count,
                    max_concurrent=self._max_concurrent,
                    queue_size=self._queue_size,
                )
            if self._max_queue == 0 and self._active_count >= self._max_concurrent:
                self._total_rejected += 1
                raise BulkheadFullError(
                    self._name,
                    active=self._active_count,
                    max_concurrent=self._max_concurrent,
                    queue_size=self._queue_size,
                )

        # Track whether we go straight in or get queued
        was_queued = False
        with self._lock:
            if self._active_count < self._max_concurrent:
                self._active_count += 1
                self._total_accepted += 1
            else:
                if self._queue_size >= self._max_queue:
                    self._total_rejected += 1
                    raise BulkheadFullError(
                        self._name,
                        active=self._active_count,
                        max_concurrent=self._max_concurrent,
                        queue_size=self._queue_size,
                    )
                self._queue_size += 1
                self._total_accepted += 1
                was_queued = True

        # Acquire the async semaphore with timeout
        try:
            await asyncio.wait_for(
                self._async_semaphore.acquire(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            with self._lock:
                if was_queued:
                    self._queue_size -= 1
                self._total_rejected += 1
            raise BulkheadFullError(
                self._name,
                active=self._active_count,
                max_concurrent=self._max_concurrent,
                queue_size=self._queue_size,
            )

        # Transition from queued to active (semaphore acquired)
        if was_queued:
            with self._lock:
                self._queue_size -= 1
                self._active_count += 1

        try:
            yield
        except Exception:
            with self._lock:
                self._total_errors += 1
            raise
        finally:
            self._async_semaphore.release()
            with self._lock:
                self._active_count -= 1
                self._total_completed += 1

    # ----------------------------------------------------------
    #  Dunder helpers
    # ----------------------------------------------------------

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"Bulkhead(name={self._name!r}, "
                f"active={self._active_count}/{self._max_concurrent}, "
                f"queue={self._queue_size})"
            )
