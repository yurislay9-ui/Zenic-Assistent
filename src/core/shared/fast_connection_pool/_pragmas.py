"""
FastConnectionPool — PRAGMA Configuration and Statistics.

Contains ARM-optimized SQLite PRAGMA settings and the PoolStats
dataclass for per-database pool statistics.
"""

import sqlite3
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "_ARM_PRAGMAS",
    "_apply_pragmas",
    "PoolStats",
]


# ============================================================
#  PRAGMA Configuration for ARM/Mobile
# ============================================================

_ARM_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA cache_size=-8192",       # 8MB cache (doubled from 4MB)
    "PRAGMA synchronous=NORMAL",     # Safe with WAL, fast
    "PRAGMA temp_store=MEMORY",      # Temp tables in RAM
    "PRAGMA mmap_size=67108864",     # 64MB memory-mapped I/O
    "PRAGMA wal_autocheckpoint=1000",# Auto-checkpoint every 1000 frames
    "PRAGMA busy_timeout=5000",      # 5s lock timeout
    "PRAGMA page_size=4096",         # Optimal for flash storage
    "PRAGMA foreign_keys=ON",        # Enforce referential integrity
]


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply optimized PRAGMA settings to a connection."""
    for pragma in _ARM_PRAGMAS:
        try:
            conn.execute(pragma)
        except sqlite3.Error as e:
            logger.debug("PRAGMA failed: %s — %s", pragma, e)


# ============================================================
#  Connection Statistics
# ============================================================

@dataclass
class PoolStats:
    """Statistics for a single database pool."""
    db_name: str = ""
    total_gets: int = 0
    thread_local_hits: int = 0
    pool_hits: int = 0
    misses: int = 0
    active_connections: int = 0
    total_commits: int = 0
    batch_commits: int = 0
    reconnections: int = 0
    last_used: float = 0.0

    @property
    def hit_rate(self) -> float:
        total = self.thread_local_hits + self.pool_hits
        return total / max(self.total_gets, 1)
