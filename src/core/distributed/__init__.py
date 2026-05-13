"""
ZENIC-AGENTS - Distributed Orchestration (Phase 4)

Transforms single-process patterns into distributed, multi-node capable
components backed by PostgreSQL (primary) and Redis (optional) for
coordination state.

Package Contents:
    Backend Layer:
        - CoordinationBackend: Abstract coordination backend interface
        - PgBackend: PostgreSQL-backed coordination (production)
        - MemoryBackend: In-process coordination (dev/testing/fallback)

    Core Components:
        - DistributedTaskQueue: Persistent task queue with priority + leasing
        - DistributedWorker: Worker with heartbeats, auto-discovery, work-stealing
        - DistributedSagaCoordinator: Cross-process SAGA with persisted state
        - DistributedCircuitBreaker: Shared-state circuit breaker across nodes
        - LeaderElection: PostgreSQL advisory-lock based leader election
        - DistributedLockManager: Cross-node distributed locking
        - ClusterTopology: Node registration, heartbeat, and topology management

Design Principles:
    - PostgreSQL as primary coordination backend (already in docker-compose)
    - Redis as optional acceleration layer (pub/sub, caching)
    - Graceful degradation: falls back to single-process if no DB available
    - ARM/RAM compatible: works on Android/Termux with 500MB RAM
    - All DB operations protected by retry + circuit breaker patterns
    - Correct imports, type hints, and wiring throughout

Usage::

    from src.core.distributed import DistributedTaskQueue, DistributedWorker
    from src.core.distributed import DistributedSagaCoordinator
    from src.core.distributed import LeaderElection, ClusterTopology
"""

# ============================================================
#  BACKEND LAYER
# ============================================================

from .backend import (
    CoordinationBackend,
    BackendConfig,
    BackendType,
)

# Lazy imports for PostgreSQL and Memory backends — they are accessed
# through CoordinationBackend.create() factory method to avoid
# import-time dependency on psycopg2/asyncpg when not needed.

# ============================================================
#  CORE COMPONENTS
# ============================================================

from .task_queue import (
    DistributedTaskQueue,
    TaskMessage,
    TaskStatus,
    TaskPriority,
)

from .worker import (
    DistributedWorker,
    WorkerState,
    WorkerConfig,
)

from .saga_coordinator import (
    DistributedSagaCoordinator,
    DistributedSagaStep,
    DistributedSagaState,
)

from .circuit_breaker_distributed import (
    DistributedCircuitBreaker,
    SharedCircuitState,
)

from .leader_election import (
    LeaderElection,
    LeadershipState,
)

from .lock_manager import (
    DistributedLockManager,
    DistributedLock,
)

from .topology import (
    ClusterTopology,
    NodeInfo,
    NodeState,
)

# ============================================================
#  PUBLIC API
# ============================================================

__all__ = [
    # Backend
    "CoordinationBackend",
    "BackendConfig",
    "BackendType",
    # Task Queue
    "DistributedTaskQueue",
    "TaskMessage",
    "TaskStatus",
    "TaskPriority",
    # Worker
    "DistributedWorker",
    "WorkerState",
    "WorkerConfig",
    # Saga
    "DistributedSagaCoordinator",
    "DistributedSagaStep",
    "DistributedSagaState",
    # Circuit Breaker
    "DistributedCircuitBreaker",
    "SharedCircuitState",
    # Leader Election
    "LeaderElection",
    "LeadershipState",
    # Lock Manager
    "DistributedLockManager",
    "DistributedLock",
    # Topology
    "ClusterTopology",
    "NodeInfo",
    "NodeState",
]
