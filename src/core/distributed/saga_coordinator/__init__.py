"""
ZENIC-AGENTS - Distributed Saga Coordinator

Cross-process SAGA pattern implementation with persisted state.
Unlike the single-process Saga in patterns/orchestration/saga.py,
this coordinator:

- Persists saga state to the CoordinationBackend (PostgreSQL)
- Supports saga execution across multiple worker processes
- Enables saga recovery after process crashes
- Provides saga status queries for observability
- Supports distributed compensation across nodes

Integration with DistributedTaskQueue:
    Each saga step is dispatched as a task to the queue. Workers
    execute the step and report results. The coordinator advances
    the saga based on step outcomes.

Designed for PostgreSQL (production) and MemoryBackend (dev/testing).
"""

import logging
from typing import Any, Dict

from ._types import DistributedSagaState, DistributedSagaStep
from ..backend import CoordinationBackend
from ..task_queue import DistributedTaskQueue, TaskMessage, TaskPriority

logger = logging.getLogger("zenic_agents.distributed.saga_coordinator")

__all__ = [
    "DistributedSagaCoordinator",
    "DistributedSagaStep",
    "DistributedSagaState",
]


# ============================================================
#  DISTRIBUTED SAGA COORDINATOR
# ============================================================


from ._core_mixin import DistributedSagaCoordinatorCoreMixin
from ._extra_mixin import DistributedSagaCoordinatorExtraMixin


class DistributedSagaCoordinator(DistributedSagaCoordinatorCoreMixin, DistributedSagaCoordinatorExtraMixin):
    """
    Coordinates multi-step distributed operations with automatic rollback.

    Each saga is persisted to the CoordinationBackend. Steps are dispatched
    as tasks to the DistributedTaskQueue. Workers execute steps and report
    results. The coordinator advances the saga based on outcomes.

    On failure, completed steps are compensated in reverse order.
    Each compensation is also dispatched as a task.

    Recovery:
        If the coordinator process crashes, saga state is preserved
        in the backend. On restart, the coordinator can resume sagas
        that were in RUNNING or COMPENSATING state.

    Usage::

        coordinator = DistributedSagaCoordinator(
            backend=backend,
            task_queue=queue,
        )

        saga_id = await coordinator.start_saga(
            name="create_order",
            steps=[
                DistributedSagaStep(
                    name="reserve_inventory",
                    action_task_type="inventory_reserve",
                    compensation_task_type="inventory_release",
                ),
                DistributedSagaStep(
                    name="charge_payment",
                    action_task_type="payment_charge",
                    compensation_task_type="payment_refund",
                ),
            ],
            initial_context={"order_id": "ORD-123"},
        )

        # Workers execute steps and report:
        await coordinator.report_step_result(
            saga_id, "reserve_inventory", success=True, result={"reserved": 5}
        )

    Thread Safety:
        The coordinator is thread-safe. Backend operations handle
        concurrency through the backend's locking mechanisms.
    """

    def __init__(
        self,
        backend: CoordinationBackend,
        task_queue: DistributedTaskQueue,
        queue_name: str = "saga",
        default_step_timeout: float = 300.0,
    ) -> None:
        """
        Initialize the distributed saga coordinator.

        Args:
            backend: Coordination backend for state persistence.
            task_queue: Task queue for dispatching step tasks.
            queue_name: Queue name for saga step tasks.
            default_step_timeout: Default step timeout in seconds.
        """
        self._backend = backend
        self._task_queue = task_queue
        self._queue_name = queue_name
        self._default_step_timeout = default_step_timeout

        # In-memory cache of active sagas being coordinated
        self._active_sagas: Dict[str, Dict[str, Any]] = {}

    # ----------------------------------------------------------
    #  SAGA LIFECYCLE
    # ----------------------------------------------------------
