"""
ZENIC-AGENTS - Concurrency Pattern: Read-Write Lock

Reader-writer lock with **writer preference** to prevent starvation.

Multiple readers can hold the lock simultaneously, but writers get
exclusive access.  When a writer is waiting, new readers are blocked
so that writers are not starved by a continuous stream of readers.

Supports both synchronous (threading) and asynchronous (asyncio) usage.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ReadWriteLock:
    """
    Read-write lock with writer preference.

    Synchronous usage::

        rwl = ReadWriteLock()
        with rwl.acquire_read():
            # multiple readers allowed
            ...
        with rwl.acquire_write():
            # exclusive access
            ...

    Asynchronous usage::

        async with rwl.acquire_read_async():
            ...
        async with rwl.acquire_write_async():
            ...
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._active_readers: int = 0
        self._active_writers: int = 0
        self._waiting_readers: int = 0
        self._waiting_writers: int = 0
        # Async counterparts
        self._async_lock = asyncio.Lock()
        self._async_readers: int = 0
        self._async_writers: int = 0
        self._async_waiting_readers: int = 0
        self._async_waiting_writers: int = 0
        self._async_can_read = asyncio.Condition(self._async_lock)
        self._async_can_write = asyncio.Condition(self._async_lock)

    # ------------------------------------------------------------------
    # Synchronous read lock
    # ------------------------------------------------------------------

    @contextmanager
    def acquire_read(self):
        """
        Context manager that acquires a **read** lock.

        Multiple readers can hold the lock concurrently.  Blocks only
        if a writer is active **or** if a writer is waiting (writer
        preference).
        """
        with self._cond:
            self._waiting_readers += 1
            while self._active_writers > 0 or self._waiting_writers > 0:
                self._cond.wait()
            self._waiting_readers -= 1
            self._active_readers += 1

        try:
            yield
        finally:
            with self._cond:
                self._active_readers -= 1
                if self._active_readers == 0:
                    self._cond.notify_all()

    # ------------------------------------------------------------------
    # Synchronous write lock
    # ------------------------------------------------------------------

    @contextmanager
    def acquire_write(self):
        """
        Context manager that acquires a **write** lock.

        Only one writer can hold the lock, and no readers may be active.
        Writers have priority: once a writer is waiting, new readers
        are blocked until all waiting writers have been served.
        """
        with self._cond:
            self._waiting_writers += 1
            while self._active_readers > 0 or self._active_writers > 0:
                self._cond.wait()
            self._waiting_writers -= 1
            self._active_writers += 1

        try:
            yield
        finally:
            with self._cond:
                self._active_writers -= 1
                self._cond.notify_all()

    # ------------------------------------------------------------------
    # Async read lock
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def acquire_read_async(self):
        """
        Async context manager that acquires a **read** lock.

        See :meth:`acquire_read` for semantics.
        """
        async with self._async_can_read:
            self._async_waiting_readers += 1
            while self._async_writers > 0 or self._async_waiting_writers > 0:
                await self._async_can_read.wait()
            self._async_waiting_readers -= 1
            self._async_readers += 1

        try:
            yield
        finally:
            async with self._async_can_read:
                self._async_readers -= 1
                if self._async_readers == 0:
                    self._async_can_read.notify_all()
                    self._async_can_write.notify_all()

    # ------------------------------------------------------------------
    # Async write lock
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def acquire_write_async(self):
        """
        Async context manager that acquires a **write** lock.

        See :meth:`acquire_write` for semantics.
        """
        async with self._async_can_write:
            self._async_waiting_writers += 1
            while self._async_readers > 0 or self._async_writers > 0:
                await self._async_can_write.wait()
            self._async_waiting_writers -= 1
            self._async_writers += 1

        try:
            yield
        finally:
            async with self._async_can_write:
                self._async_writers -= 1
                self._async_can_write.notify_all()
                self._async_can_read.notify_all()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active_readers(self) -> int:
        """Number of threads currently holding a read lock."""
        with self._cond:
            return self._active_readers

    @property
    def active_writers(self) -> int:
        """Number of threads currently holding a write lock."""
        with self._cond:
            return self._active_writers

    @property
    def waiting_readers(self) -> int:
        """Number of threads waiting to acquire a read lock."""
        with self._cond:
            return self._waiting_readers

    @property
    def waiting_writers(self) -> int:
        """Number of threads waiting to acquire a write lock."""
        with self._cond:
            return self._waiting_writers

    def __repr__(self) -> str:
        return (
            f"ReadWriteLock(readers={self._active_readers}, "
            f"writers={self._active_writers}, "
            f"waiting_r={self._waiting_readers}, "
            f"waiting_w={self._waiting_writers})"
        )
