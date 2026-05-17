"""Distributed Lock instance."""

import logging
import threading
from typing import Any, Optional
from ..backend import CoordinationBackend
logger = logging.getLogger("core.distributed.lock_manager._lock")

class DistributedLock:
    """
    Distributed lock instance returned by DistributedLockManager.acquire().

    Supports the context manager protocol for automatic release::

        async with lock_manager.acquire_context("my_lock") as lock:
            # Critical section
            do_exclusive_work()
        # Lock automatically released

    Attributes:
        lock_name: Name of the lock.
        holder_id: ID of the lock holder.
        ttl_seconds: Lock time-to-live.
        acquired: Whether the lock is currently held.
    """

    def __init__(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float,
        backend: CoordinationBackend,
    ) -> None:
        self._lock_name = lock_name
        self._holder_id = holder_id
        self._ttl_seconds = ttl_seconds
        self._backend = backend
        self._acquired = False
        self._extension_thread: Optional[threading.Thread] = None
        self._stop_extension = threading.Event()

    @property
    def lock_name(self) -> str:
        """Name of the lock."""
        return self._lock_name

    @property
    def holder_id(self) -> str:
        """ID of the lock holder."""
        return self._holder_id

    @property
    def ttl_seconds(self) -> float:
        """Lock TTL in seconds."""
        return self._ttl_seconds

    @property
    def acquired(self) -> bool:
        """Whether the lock is currently held."""
        return self._acquired

    # ----------------------------------------------------------
    #  CONTEXT MANAGER (sync)
    # ----------------------------------------------------------

    def __enter__(self) -> "DistributedLock":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release_sync()

    # ----------------------------------------------------------
    #  RELEASE
    # ----------------------------------------------------------

    async def release(self) -> bool:
        """
        Release the lock asynchronously.

        Returns:
            True if the lock was released.
        """
        if not self._acquired:
            return False

        self._stop_extension.set()
        success = await self._backend.release_lock(
            self._lock_name, self._holder_id,
        )

        if success:
            self._acquired = False
            logger.debug(
                "DistributedLock: Released '%s' (holder=%s)",
                self._lock_name, self._holder_id,
            )
        return success

    def release_sync(self) -> bool:
        """Synchronous release wrapper."""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.release())
            finally:
                loop.close()
        except Exception as exc:
            logger.error(
                "DistributedLock: Release error for '%s': %s",
                self._lock_name, exc,
            )
            return False

    # ----------------------------------------------------------
    #  EXTENSION
    # ----------------------------------------------------------

    async def extend(self, additional_seconds: float = 30.0) -> bool:
        """
        Extend the lock's TTL.

        Args:
            additional_seconds: Extra time to add.

        Returns:
            True if the lock was extended.
        """
        if not self._acquired:
            return False
        return await self._backend.extend_lock(
            self._lock_name, self._holder_id, additional_seconds,
        )

    def start_auto_extension(self, interval_seconds: float = 10.0) -> None:
        """
        Start a background thread that automatically extends the lock.

        Args:
            interval_seconds: How often to extend.
        """
        if self._extension_thread and self._extension_thread.is_alive():
            return

        self._stop_extension.clear()
        self._extension_thread = threading.Thread(
            target=self._auto_extend_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._extension_thread.start()

    def _auto_extend_loop(self, interval: float) -> None:
        """Background loop that extends the lock TTL."""
        while not self._stop_extension.is_set():
            if self._acquired:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            self.extend(self._ttl_seconds * 0.5)
                        )
                    finally:
                        loop.close()
                except Exception as exc:
                    logger.warning(
                        "DistributedLock: Auto-extend failed for '%s': %s",
                        self._lock_name, exc,
                    )
            self._stop_extension.wait(timeout=interval)


# ============================================================
#  DISTRIBUTED LOCK MANAGER
# ============================================================
