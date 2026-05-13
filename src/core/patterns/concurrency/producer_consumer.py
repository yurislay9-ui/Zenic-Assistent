"""
ZENIC-AGENTS - Concurrency Pattern: Producer-Consumer

Bounded-buffer producer-consumer pattern with graceful shutdown.
Supports both sync and async producers.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import asyncio
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ProducerConsumer:
    """
    Bounded-buffer producer-consumer pattern.

    Producers call :meth:`produce` to add items to an internal buffer.
    One or more consumer threads dequeue items and pass them to a
    registered consumer function.

    Supports both synchronous and asynchronous (``async def``) consumer
    functions.

    Usage::

        pc = ProducerConsumer(buffer_size=50, num_consumers=2)
        pc.set_consumer(lambda item: process(item))
        pc.start()
        for item in data_source:
            pc.produce(item)
        pc.stop()   # graceful — drains remaining items
    """

    def __init__(
        self,
        buffer_size: int = 50,
        num_consumers: int = 2,
    ) -> None:
        """
        Args:
            buffer_size: Maximum items in the bounded buffer (0 = unbounded).
            num_consumers: Number of consumer threads to start.
        """
        self._buffer: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._num_consumers = num_consumers
        self._consumer_fn: Optional[Callable[..., Any]] = None
        self._consumers: list = []
        self._running = False
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._produced = 0
        self._consumed = 0
        self._errors = 0
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_consumer(self, fn: Callable[..., Any]) -> None:
        """
        Set the consumer function.

        Args:
            fn: Callable that processes a single item.  May be a regular
                function or an ``async def`` coroutine.

        Raises:
            ValueError: If *fn* is not callable.
            RuntimeError: If the producer-consumer is already running.
        """
        if not callable(fn):
            raise ValueError("ProducerConsumer: consumer fn must be callable")
        if self._running:
            raise RuntimeError("ProducerConsumer: cannot set consumer while running")
        self._consumer_fn = fn

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def produce(self, item: Any) -> None:
        """
        Add *item* to the buffer.  Blocks if the buffer is full.

        Args:
            item: Any object to be consumed.

        Raises:
            RuntimeError: If the producer-consumer is not running.
        """
        if not self._running:
            raise RuntimeError("ProducerConsumer: not running — call start() first")
        self._buffer.put(item, block=True)
        with self._stats_lock:
            self._produced += 1

    async def produce_async(self, item: Any) -> None:
        """
        Async version of :meth:`produce`.

        Uses ``asyncio.to_thread`` to avoid blocking the event loop.
        """
        if not self._running:
            raise RuntimeError("ProducerConsumer: not running — call start() first")
        await asyncio.to_thread(self._buffer.put, item, True)
        with self._stats_lock:
            self._produced += 1

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the consumer threads.

        Raises:
            RuntimeError: If already running or no consumer function set.
        """
        if self._running:
            raise RuntimeError("ProducerConsumer: already running")
        if self._consumer_fn is None:
            raise RuntimeError("ProducerConsumer: no consumer function set — call set_consumer() first")

        self._running = True
        self._stop_event.clear()

        for i in range(self._num_consumers):
            t = threading.Thread(
                target=self._consumer_loop,
                name=f"pc-consumer-{i}",
                daemon=True,
            )
            self._consumers.append(t)
            t.start()

        logger.debug(
            "ProducerConsumer: started %d consumers", self._num_consumers
        )

    def stop(self) -> None:
        """
        Gracefully stop the producer-consumer.

        Signals consumers to finish and waits for them to drain the
        remaining items in the buffer before exiting.
        """
        if not self._running:
            return

        logger.debug("ProducerConsumer: stopping — draining remaining items")
        self._stop_event.set()

        # Push sentinel values so consumers wake up
        for _ in self._consumers:
            try:
                self._buffer.put_nowait(None)  # type: ignore[arg-type]
            except queue.Full:
                break

        for t in self._consumers:
            t.join(timeout=30.0)

        self._running = False
        self._consumers.clear()
        logger.debug("ProducerConsumer: stopped")

    @property
    def is_running(self) -> bool:
        """Return True if the producer-consumer is active."""
        return self._running

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._stats_lock:
            return {
                "produced": self._produced,
                "consumed": self._consumed,
                "errors": self._errors,
                "buffer_size": self._buffer.qsize(),
                "running": self._running,
                "num_consumers": self._num_consumers,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _consumer_loop(self) -> None:
        """Main loop for each consumer thread."""
        while not self._stop_event.is_set() or not self._buffer.empty():
            try:
                item = self._buffer.get(block=True, timeout=0.5)
            except queue.Empty:
                continue

            if item is None and self._stop_event.is_set():
                # Sentinel during shutdown
                break

            try:
                result = self._consumer_fn(item)  # type: ignore[misc]
                # If the consumer is async, run it in a new event loop
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # We're inside an existing loop — use nest_asyncio fallback
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                                pool.submit(asyncio.run, result).result()
                        else:
                            loop.run_until_complete(result)
                    except RuntimeError:
                        asyncio.run(result)

                with self._stats_lock:
                    self._consumed += 1
            except Exception as exc:
                with self._stats_lock:
                    self._errors += 1
                logger.error("ProducerConsumer: consumer error – %s", exc)
