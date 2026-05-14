"""Distributed Lock Manager."""

import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional
from .backend import CoordinationBackend
from ._lock import DistributedLock

class DistributedLockManager:
    """
    Manager for distributed locks across multiple nodes.

    Provides a simple interface for acquiring, releasing, and
    managing named distributed locks backed by the CoordinationBackend.

    Usage::

        lock_mgr = DistributedLockManager(
            backend=backend,
            default_ttl=60.0,
        )

        # Non-blocking acquire
        lock = await lock_mgr.acquire("migration_lock")
        if lock:
            try:
                run_migration()
            finally:
                await lock.release()

        # Blocking acquire with timeout
        lock = await lock_mgr.acquire(
            "migration_lock",
            timeout_seconds=30.0,
        )

        # Context manager (sync)
        with lock_mgr.acquire_sync("migration_lock"):
            run_migration()
    """

    def __init__(
        self,
        backend: CoordinationBackend,
        holder_id: Optional[str] = None,
        default_ttl: float = 60.0,
    ) -> None:
        """
        Initialize the lock manager.

        Args:
            backend: Coordination backend for lock state.
            holder_id: Default holder ID (auto-generated if empty).
            default_ttl: Default lock TTL in seconds.
        """
        self._backend = backend
        self._holder_id = holder_id or f"holder-{uuid.uuid4().hex[:8]}"
        self._default_ttl = default_ttl

        # Track held locks for cleanup
        self._held_locks: Dict[str, DistributedLock] = {}
        self._lock = threading.Lock()

    @property
    def holder_id(self) -> str:
        """Default holder ID."""
        return self._holder_id

    # ----------------------------------------------------------
    #  ACQUIRE
    # ----------------------------------------------------------

    async def acquire(
        self,
        lock_name: str,
        ttl_seconds: Optional[float] = None,
        timeout_seconds: float = 0.0,
        holder_id: Optional[str] = None,
    ) -> Optional[DistributedLock]:
        """
        Acquire a distributed lock.

        Args:
            lock_name: Name of the lock to acquire.
            ttl_seconds: Lock TTL (default from config).
            timeout_seconds: How long to wait (0 = no wait).
            holder_id: Override holder ID.

        Returns:
            DistributedLock if acquired, None if not.
        """
        ttl = ttl_seconds or self._default_ttl
        holder = holder_id or self._holder_id

        success = await self._backend.acquire_lock(
            lock_name=lock_name,
            holder_id=holder,
            ttl_seconds=ttl,
            timeout_seconds=timeout_seconds,
        )

        if not success:
            return None

        lock = DistributedLock(
            lock_name=lock_name,
            holder_id=holder,
            ttl_seconds=ttl,
            backend=self._backend,
        )
        lock._acquired = True

        with self._lock:
            self._held_locks[lock_name] = lock

        logger.debug(
            "LockManager: Acquired '%s' (holder=%s, ttl=%.0fs)",
            lock_name, holder, ttl,
        )
        return lock

    def acquire_sync(
        self,
        lock_name: str,
        ttl_seconds: Optional[float] = None,
        timeout_seconds: float = 0.0,
    ) -> Optional[DistributedLock]:
        """Synchronous acquire wrapper."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.acquire(lock_name, ttl_seconds, timeout_seconds)
            )
        finally:
            loop.close()

    # ----------------------------------------------------------
    #  ACQUIRE CONTEXT (ASYNC)
    # ----------------------------------------------------------

    class _AsyncLockContext:
        """Async context manager for distributed locks."""

        def __init__(self, lock: Optional[DistributedLock]) -> None:
            self._lock = lock

        async def __aenter__(self) -> Optional[DistributedLock]:
            return self._lock

        async def __aexit__(self, *args: Any) -> None:
            if self._lock and self._lock.acquired:
                await self._lock.release()

    async def acquire_context(
        self,
        lock_name: str,
        ttl_seconds: Optional[float] = None,
        timeout_seconds: float = 0.0,
    ) -> "_AsyncLockContext":
        """
        Acquire a lock as an async context manager.

        Usage::

            async with lock_mgr.acquire_context("my_lock") as lock:
                if lock:
                    do_exclusive_work()
        """
        lock = await self.acquire(lock_name, ttl_seconds, timeout_seconds)
        return self._AsyncLockContext(lock)

    # ----------------------------------------------------------
    #  QUERY
    # ----------------------------------------------------------

    async def is_locked(self, lock_name: str) -> bool:
        """Check if a lock is currently held."""
        return await self._backend.is_locked(lock_name)

    # ----------------------------------------------------------
    #  CLEANUP
    # ----------------------------------------------------------

    async def release_all(self) -> int:
        """
        Release all locks held by this manager.

        Returns:
            Number of locks released.
        """
        released = 0
        with self._lock:
            for lock_name, lock in list(self._held_locks.items()):
                if lock.acquired:
                    success = await lock.release()
                    if success:
                        released += 1
            self._held_locks.clear()
        return released

    @property
    def stats(self) -> Dict[str, Any]:
        """Lock manager statistics."""
        with self._lock:
            return {
                "holder_id": self._holder_id,
                "default_ttl": self._default_ttl,
                "held_locks": len(self._held_locks),
                "lock_names": list(self._held_locks.keys()),
            }
