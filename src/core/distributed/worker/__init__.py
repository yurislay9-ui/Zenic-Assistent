"""
ZENIC-AGENTS - Distributed Worker

Long-running worker process that pulls tasks from a DistributedTaskQueue,
executes them, and reports results. Features:

- Heartbeat-based liveness tracking
- Lease renewal for long-running tasks
- Configurable task type specialization
- Graceful shutdown with task re-queueing
- Work-stealing from overloaded peers
- Auto-registration in cluster topology
- Resource-aware task execution (respects ResourceGovernor)

Designed for PostgreSQL (production) and MemoryBackend (dev/testing).

PERFORMANCE (H-07 fix): Reuses a single asyncio event loop per thread
instead of creating/destroying a new loop for every async operation.
"""

import logging

from ._types import WorkerState, WorkerConfig, TaskHandler
from ._helpers import _local, _run_async, _METRICS_AVAILABLE

from ..backend import CoordinationBackend
from ..task_queue import DistributedTaskQueue, TaskStatus

logger = logging.getLogger("zenic_agents.distributed.worker")

__all__ = [
    "DistributedWorker",
    "WorkerState",
    "WorkerConfig",
]


# ============================================================
#  DISTRIBUTED WORKER
# ============================================================


from ._core_mixin import DistributedWorkerCoreMixin
from ._extra_mixin import DistributedWorkerExtraMixin


class DistributedWorker(DistributedWorkerCoreMixin, DistributedWorkerExtraMixin):
    """Distributed worker that consumes tasks from a DistributedTaskQueue.

    The worker runs a continuous loop that:
    1. Sends periodic heartbeats to the cluster topology
    2. Polls for available tasks from configured queues
    3. Claims and executes tasks with lease management
    4. Reports results (complete/fail) back to the queue
    5. Renews leases for long-running tasks
    6. Gracefully shuts down when signalled
    """
    pass
