"""
ZENIC-AGENTS - Distributed Lock Manager

Cross-node distributed locking using the CoordinationBackend.
Ensures mutual exclusion across multiple processes and nodes.

Features:
    - Named locks with configurable TTL
    - Blocking and non-blocking acquisition
    - Lock extension for long-running operations
    - Context manager protocol for automatic release
    - Deadlock prevention via TTL expiration
    - Re-entrant lock support (same holder can re-acquire)

Use Cases:
    - Exclusive database migrations
    - Singleton task execution (only one node runs)
    - Rate-limited resource access
    - Distributed file writes
    - Configuration change coordination
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional
from ..backend import CoordinationBackend
from ._core import DistributedLockManager  # type: ignore[import-unresolved]
from ._lock import DistributedLock  # type: ignore[import-unresolved]


logger = logging.getLogger(__name__)

__all__ = [
    "DistributedLockManager",
    "DistributedLock",
]


# ============================================================
#  DISTRIBUTED LOCK (Context Manager)
# ============================================================

