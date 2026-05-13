"""
ZENIC-AGENTS - PostgreSQL Coordination Backend

Production coordination backend using PostgreSQL for distributed state.
Leverages:
    - pg_advisory_lock for distributed locking
    - SELECT ... FOR UPDATE SKIP LOCKED for task queue dequeue
    - Transactional guarantees for saga state
    - Optimistic concurrency control for circuit breaker state

Requires:
    - psycopg2 (sync) or asyncpg (async) for database access
    - PostgreSQL 12+ with the zenic_coordination schema

Schema is auto-created on connect() if tables don't exist.
"""

import logging
from typing import Any, Optional

from ..backend import BackendConfig, CoordinationBackend
from ._schema import PgConnectionMixin
from ._task_mixin import PgTaskMixin
from ._lock_election_mixin import PgLockElectionMixin
from ._saga_node_mixin import PgCircuitMixin, PgSagaMixin, PgNodeMixin

logger = logging.getLogger("zenic_agents.distributed.pg_backend")

__all__ = ["PgBackend"]


class PgBackend(
    PgConnectionMixin,
    PgTaskMixin,
    PgLockElectionMixin,
    PgCircuitMixin,
    PgSagaMixin,
    PgNodeMixin,
    CoordinationBackend,
):
    """
    PostgreSQL-backed coordination backend for production deployments.

    Uses psycopg2 for synchronous database access. All operations are
    wrapped in proper transaction management with retry logic.

    The schema is auto-created on connect() using CREATE IF NOT EXISTS,
    making it safe to run on every startup.

    Connection pooling is managed per-instance with thread-safe access.
    """

    def __init__(self, config: BackendConfig) -> None:
        super().__init__(config)
        self._pool: Optional[Any] = None  # psycopg2 connection pool
        self._conn = None  # Single connection fallback
