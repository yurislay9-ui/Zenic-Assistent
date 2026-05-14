"""CoordinationBackend - Core methods."""

import logging
from typing import Any, Dict, List, Optional

from ._types import BackendConfig, BackendType

logger = logging.getLogger("zenic_agents.distributed.backend")


class CoordinationBackendCoreMixin:
    """Core methods."""

    def __init__(self, config: BackendConfig) -> None:
        self._config = config
        self._node_id = config.node_id
        self._connected = False
    def node_id(self) -> str:
        """Unique identifier for this node."""
        return self._node_id
    def config(self) -> BackendConfig:
        """Backend configuration."""
        return self._config
    def is_connected(self) -> bool:
        """Whether the backend is currently connected."""
        return self._connected
    def create(config: BackendConfig) -> "CoordinationBackend":
        """
        Factory method: create the appropriate backend from config.

        Falls back to MemoryBackend if PostgreSQL is requested but
        dependencies are unavailable.

        Args:
            config: Backend configuration.

        Returns:
            A concrete CoordinationBackend instance.
        """
        if config.backend_type == BackendType.POSTGRESQL:
            try:
                from .pg_backend import PgBackend
                backend = PgBackend(config)
                logger.info(
                    "CoordinationBackend: Created PostgreSQL backend "
                    "(node_id=%s)", config.node_id,
                )
                return backend
            except ImportError as exc:
                logger.warning(
                    "CoordinationBackend: PostgreSQL dependencies not "
                    "available (%s), falling back to MemoryBackend", exc,
                )
            except Exception as exc:
                logger.warning(
                    "CoordinationBackend: PostgreSQL backend creation "
                    "failed (%s), falling back to MemoryBackend", exc,
                )

        # Memory backend (explicit or fallback)
        from .memory_backend import MemoryBackend
        logger.info(
            "CoordinationBackend: Created Memory backend "
            "(node_id=%s)", config.node_id,
        )
        return MemoryBackend(config)
    async def connect(self) -> None:
        """
        Initialize the backend connection.

        For PostgreSQL: establishes connection pool and creates
        coordination tables if they don't exist.

        For Memory: initializes in-memory data structures.
        """
    async def disconnect(self) -> None:
        """Close the backend connection and release resources."""
    async def health_check(self) -> Dict[str, Any]:
        """
        Check backend health.

        Returns:
            Dict with at minimum:
            - healthy: bool
            - backend_type: str
            - latency_ms: float (round-trip time for a simple operation)
        """
    async def enqueue_task(
        self,
        queue_name: str,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        delay_until: Optional[float] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """
        Add a task to the named queue.

        Args:
            queue_name: Logical queue name (e.g., "pipeline", "generation").
            task_id: Unique task identifier.
            task_type: Task type for dispatch routing.
            payload: Task payload (JSON-serializable dict).
            priority: Higher priority = dequeued first (default 0).
            delay_until: Unix timestamp; task not available before this time.
            tenant_id: Optional tenant for multi-tenant isolation.

        Returns:
            True if the task was enqueued successfully.
        """
    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        lease_seconds: float = 120.0,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically claim the highest-priority available task from the queue.

        Uses SELECT ... FOR UPDATE SKIP LOCKED (PostgreSQL) or equivalent
        to ensure exactly-once task assignment.

        Args:
            queue_name: Logical queue to dequeue from.
            worker_id: ID of the worker claiming the task.
            lease_seconds: How long the lease lasts before the task
                           becomes available again.
            task_types: If set, only dequeue tasks matching these types.
            tenant_id: If set, only dequeue tasks for this tenant.

        Returns:
            Dict with task details, or None if no task is available.
        """
    async def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: The task to complete.
            result: Optional result payload.

        Returns:
            True if the task was found and completed.
        """
    async def fail_task(
        self,
        task_id: str,
        error: str,
        retryable: bool = True,
    ) -> bool:
        """
        Mark a task as failed.

        Args:
            task_id: The task that failed.
            error: Error message.
            retryable: If True, the task may be re-attempted.

        Returns:
            True if the task was found and marked as failed.
        """
    async def renew_lease(self, task_id: str, additional_seconds: float = 60.0) -> bool:
        """
        Extend the lease on a currently-leased task.

        Args:
            task_id: The task whose lease to extend.
            additional_seconds: How much more time to add.

        Returns:
            True if the lease was extended successfully.
        """
    async def expire_leases(self, queue_name: str) -> int:
        """
        Find and release expired task leases, making them available again.

        Should be called periodically by a coordinator or leader.

        Args:
            queue_name: The queue to scan for expired leases.

        Returns:
            Number of leases that were expired.
        """
    async def acquire_lock(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float = 60.0,
        timeout_seconds: float = 0.0,
    ) -> bool:
        """
        Acquire a distributed lock.

        Args:
            lock_name: Name of the lock.
            holder_id: ID of the lock holder (usually node_id).
            ttl_seconds: Lock time-to-live before automatic release.
            timeout_seconds: How long to wait for the lock (0 = no wait).

        Returns:
            True if the lock was acquired.
        """
    async def release_lock(self, lock_name: str, holder_id: str) -> bool:
        """
        Release a distributed lock.

        Args:
            lock_name: Name of the lock.
            holder_id: Must match the current holder.

        Returns:
            True if the lock was released (holder matched).
        """
