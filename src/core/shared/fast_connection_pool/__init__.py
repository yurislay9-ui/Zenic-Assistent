"""
FastConnectionPool - Ultra-fast SQLite connection pool for Zenic-Agents.

Replaces the 55+ raw sqlite3.connect() calls across the codebase with
a centralized, thread-safe connection pool optimized for ARM/mobile.
"""

import threading
from contextlib import contextmanager
from typing import Optional

from ._pragmas import _ARM_PRAGMAS, _apply_pragmas, PoolStats
from ._pool import FastPool

__all__ = [
    "FastPool",
    "fast_pool",
    "get_pooled_connection",
    "batch_commit",
    "close_all_pools",
]


# ============================================================
#  Global Singleton
# ============================================================

_global_pool: Optional[FastPool] = None
_pool_lock = threading.Lock()


def fast_pool() -> FastPool:
    """Get the global FastPool singleton."""
    global _global_pool
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                _global_pool = FastPool()
    return _global_pool


def get_pooled_connection(db_name: str):
    """Convenience function: get a connection from the global pool."""
    return fast_pool().get(db_name)


@contextmanager
def batch_commit(db_name: str):
    """Convenience function: batch commit context manager."""
    with fast_pool().batch_commit(db_name) as conn:
        yield conn


def close_all_pools() -> None:
    """Close the global pool."""
    global _global_pool
    if _global_pool is not None:
        _global_pool.close_all()
        _global_pool = None
