"""
FastConnectionPool — FastPool Class.

Ultra-fast SQLite connection pool with thread-local caching.
"""

import sqlite3
import threading
import time
import logging
from collections import deque
from typing import Dict, Optional, Any, List
from contextlib import contextmanager

from ._pragmas import _apply_pragmas, PoolStats

logger = logging.getLogger(__name__)

__all__ = ["FastPool"]


class FastPool:
    """
    Ultra-fast SQLite connection pool with thread-local caching.

    Architecture:
    - Layer 1: Thread-local cache (zero contention, instant access)
    - Layer 2: Shared pool (for overflow, max 5 per DB)
    - Layer 3: New connection (only on cache miss + pool empty)
    """

    def __init__(self, max_shared_per_db: int = 5, idle_timeout_s: float = 300.0):
        self._max_shared = max_shared_per_db
        self._idle_timeout = idle_timeout_s

        # Thread-local: {db_name: sqlite3.Connection}
        self._local = threading.local()

        # Shared overflow pool: {db_name: deque[sqlite3.Connection]}
        self._shared: Dict[str, deque] = {}
        self._shared_lock = threading.Lock()

        # Per-database write locks
        self._write_locks: Dict[str, threading.Lock] = {}
        self._write_lock_mutex = threading.Lock()

        # Per-database stats
        self._stats: Dict[str, PoolStats] = {}
        self._stats_lock = threading.Lock()

        # Data directory
        self._data_dir = self._get_data_dir()

        # Cleanup thread
        self._shutdown = threading.Event()
        self._cleaner = threading.Thread(
            target=self._idle_cleanup_loop,
            daemon=True,
            name="FastPool-Cleaner",
        )
        self._cleaner.start()

        # atexit cleanup
        import atexit
        atexit.register(self.close_all)

    @staticmethod
    def _get_data_dir() -> str:
        """Get the data directory path."""
        from pathlib import Path
        import os
        if 'ANDROID_ARGUMENT' in os.environ:
            try:
                from android.storage import app_storage_path
                return str(Path(app_storage_path()) / "zenic_data")
            except Exception:
                pass
        return str(Path.home() / ".zenic_agents" / "data")

    def _db_path(self, db_name: str) -> str:
        """Get full path for a database file."""
        import os
        return os.path.join(self._data_dir, db_name)

    def _get_stats(self, db_name: str) -> PoolStats:
        """Get or create stats for a database."""
        with self._stats_lock:
            if db_name not in self._stats:
                self._stats[db_name] = PoolStats(db_name=db_name)
            return self._stats[db_name]

    def _get_write_lock(self, db_name: str) -> threading.Lock:
        """Get or create a write lock for a database."""
        with self._write_lock_mutex:
            if db_name not in self._write_locks:
                self._write_locks[db_name] = threading.Lock()
            return self._write_locks[db_name]

    def _create_connection(self, db_name: str) -> sqlite3.Connection:
        """Create a new optimized SQLite connection."""
        path = self._db_path(db_name)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        return conn

    def _is_alive(self, conn: sqlite3.Connection) -> bool:
        """Check if a connection is still alive."""
        try:
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    # ─── Public API ───────────────────────────────────────────

    def get(self, db_name: str) -> sqlite3.Connection:
        """Get a connection from the pool (thread-local, auto-reused)."""
        stats = self._get_stats(db_name)
        stats.total_gets += 1
        stats.last_used = time.monotonic()

        # Layer 1: Thread-local cache
        local_pool = getattr(self._local, 'pool', None)
        if local_pool is None:
            local_pool = {}
            self._local.pool = local_pool

        if db_name in local_pool:
            conn = local_pool[db_name]
            if self._is_alive(conn):
                stats.thread_local_hits += 1
                return conn
            else:
                try:
                    conn.close()
                except Exception:
                    pass
                del local_pool[db_name]
                stats.reconnections += 1

        # Layer 2: Shared overflow pool
        with self._shared_lock:
            if db_name not in self._shared:
                self._shared[db_name] = deque()
            pool = self._shared[db_name]
            while pool:
                conn = pool.popleft()
                if self._is_alive(conn):
                    local_pool[db_name] = conn
                    stats.pool_hits += 1
                    stats.active_connections += 1
                    return conn
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    stats.reconnections += 1

        # Layer 3: New connection
        conn = self._create_connection(db_name)
        local_pool[db_name] = conn
        stats.misses += 1
        stats.active_connections += 1
        return conn

    def release(self, db_name: str, conn: sqlite3.Connection) -> None:
        """Return a connection to the shared pool."""
        with self._shared_lock:
            if db_name not in self._shared:
                self._shared[db_name] = deque()
            if len(self._shared[db_name]) < self._max_shared:
                self._shared[db_name].append(conn)
            else:
                try:
                    conn.close()
                except Exception:
                    pass

    @contextmanager
    def write(self, db_name: str):
        """Context manager for write operations (auto-commit/rollback)."""
        lock = self._get_write_lock(db_name)
        conn = self.get(db_name)
        lock.acquire()
        try:
            yield conn
            conn.commit()
            self._get_stats(db_name).total_commits += 1
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            lock.release()

    @contextmanager
    def batch_commit(self, db_name: str, batch_size: int = 100):  # noqa: ARG002
        """Context manager for batch write operations (10-50x faster)."""
        lock = self._get_write_lock(db_name)
        conn = self.get(db_name)
        lock.acquire()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
            self._get_stats(db_name).total_commits += 1
            self._get_stats(db_name).batch_commits += 1
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            lock.release()

    def checkpoint(self, db_name: str) -> None:
        """Run WAL checkpoint to truncate the WAL file."""
        conn = self.get(db_name)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as e:
            logger.debug("WAL checkpoint failed for %s: %s", db_name, e)

    def stats(self, db_name: Optional[str] = None) -> Dict[str, Any]:
        """Get pool statistics."""
        if db_name:
            s = self._get_stats(db_name)
            return {
                "db_name": s.db_name,
                "total_gets": s.total_gets,
                "thread_local_hits": s.thread_local_hits,
                "pool_hits": s.pool_hits,
                "misses": s.misses,
                "hit_rate": f"{s.hit_rate:.1%}",
                "active_connections": s.active_connections,
                "total_commits": s.total_commits,
                "batch_commits": s.batch_commits,
                "reconnections": s.reconnections,
            }
        all_stats = {}
        with self._stats_lock:
            for name, s in self._stats.items():
                all_stats[name] = {
                    "total_gets": s.total_gets,
                    "hit_rate": f"{s.hit_rate:.1%}",
                    "commits": s.total_commits,
                    "batch_commits": s.batch_commits,
                }
        return all_stats

    # ─── Lifecycle ────────────────────────────────────────────

    def close_all(self) -> None:
        """Close all connections and stop the cleaner thread."""
        self._shutdown.set()

        local_pool = getattr(self._local, 'pool', None)
        if local_pool:
            for name, conn in local_pool.items():
                try:
                    conn.close()
                except Exception:
                    pass
            local_pool.clear()

        with self._shared_lock:
            for name, pool in self._shared.items():
                while pool:
                    conn = pool.popleft()
                    try:
                        conn.close()
                    except Exception:
                        pass
            self._shared.clear()

        logger.info("FastPool: all connections closed")

    def _idle_cleanup_loop(self) -> None:
        """Background thread that cleans up idle connections."""
        while not self._shutdown.is_set():
            self._shutdown.wait(timeout=60.0)
            if self._shutdown.is_set():
                break

            now = time.monotonic()
            with self._shared_lock:
                for name, pool in list(self._shared.items()):
                    while pool:
                        stats = self._get_stats(name)
                        idle_time = now - stats.last_used
                        if idle_time < self._idle_timeout:
                            break
                        conn = pool.popleft()
                        try:
                            conn.close()
                            stats.active_connections -= 1
                        except Exception:
                            pass

    def purge_tenant(self, db_name: str, tenant_id: str, tables: List[str]) -> int:
        """Remove all rows for a tenant from specified tables (GDPR compliance)."""
        _VALID_TABLES = frozenset({
            "ast_nodes", "theorems", "ledger", "requests",
            "episodes", "patterns", "projects", "cache_entries",
        })
        total_deleted = 0
        with self.write(db_name) as conn:
            for table in tables:
                if table not in _VALID_TABLES:
                    logger.warning("purge_tenant: skipping invalid table name %r", table)
                    continue
                try:
                    cursor = conn.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ?",
                        (tenant_id,),
                    )
                    total_deleted += cursor.rowcount
                except sqlite3.Error as e:
                    logger.warning("Failed to purge tenant %s from %s.%s: %s",
                                   tenant_id, db_name, table, e)
        return total_deleted
