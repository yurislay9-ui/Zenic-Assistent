"""
ZENIC-AGENTS - In-Memory Coordination Backend

Single-process in-memory implementation of CoordinationBackend.
Used for development/testing without external dependencies,
graceful degradation when PostgreSQL is unavailable, and
single-node deployments (Android/Termux with 500MB RAM).
"""

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..backend import BackendConfig, CoordinationBackend
from ._task_lock_mixin import TaskLockMixin
from ._coord_mixin import CoordinationMixin

logger = logging.getLogger(__name__)

__all__ = ["MemoryBackend"]


class MemoryBackend(TaskLockMixin, CoordinationMixin, CoordinationBackend):
    """
    In-memory coordination backend for single-process deployments.

    All state is held in Python dicts protected by a threading.Lock.
    Suitable for development/testing and single-node deployments.
    """

    def __init__(self, config: BackendConfig) -> None:
        super().__init__(config)
        self._lock = threading.Lock()

        # Task queues: queue_name -> list of task dicts
        self._tasks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # task_id -> task dict (index for fast lookup)
        self._task_index: Dict[str, Dict[str, Any]] = {}

        # Distributed locks: lock_name -> {holder_id, expires_at}
        self._locks: Dict[str, Dict[str, Any]] = {}

        # Leader election: election_name -> {leader_id, expires_at}
        self._elections: Dict[str, Dict[str, Any]] = {}

        # Circuit breaker state: circuit_name -> {state, version, ...}
        self._circuits: Dict[str, Dict[str, Any]] = {}

        # Saga state: saga_id -> {name, status, steps, context, ...}
        self._sagas: Dict[str, Dict[str, Any]] = {}

        # Node topology: node_id -> node_info
        self._nodes: Dict[str, Dict[str, Any]] = {}

    # ----------------------------------------------------------
    #  LIFECYCLE
    # ----------------------------------------------------------

    async def connect(self) -> None:
        """Initialize in-memory data structures."""
        self._connected = True
        logger.info("MemoryBackend: Connected (node_id=%s)", self._node_id)

    async def disconnect(self) -> None:
        """Clear all state and disconnect."""
        with self._lock:
            self._tasks.clear()
            self._task_index.clear()
            self._locks.clear()
            self._elections.clear()
            self._circuits.clear()
            self._sagas.clear()
            self._nodes.clear()
        self._connected = False
        logger.info("MemoryBackend: Disconnected")

    async def health_check(self) -> Dict[str, Any]:
        """Check backend health (always healthy for in-memory)."""
        start = time.monotonic()
        with self._lock:
            _ = len(self._tasks)
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "healthy": True,
            "backend_type": "memory",
            "latency_ms": latency_ms,
            "node_id": self._node_id,
            "tasks": len(self._task_index),
            "locks": len(self._locks),
            "nodes": len(self._nodes),
        }
