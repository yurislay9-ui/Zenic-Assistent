"""DistributedWorker - Types and configuration."""

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ============================================================
#  ENUMS
# ============================================================

class WorkerState(str, enum.Enum):
    """Worker lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ============================================================
#  CONFIGURATION
# ============================================================

@dataclass
class WorkerConfig:
    """
    Configuration for DistributedWorker.

    Attributes:
        worker_id: Unique worker identifier. Auto-generated if empty.
        queue_names: List of queue names to consume from.
        task_types: If set, only process these task types.
        tenant_id: If set, only process tasks for this tenant.
        lease_seconds: Default task lease duration.
        lease_renewal_interval: How often to renew leases (seconds).
        heartbeat_interval: How often to send heartbeats (seconds).
        poll_interval: How often to poll for new tasks (seconds).
        max_concurrent_tasks: Maximum concurrent tasks (1 for now).
        lease_renewal_threshold: Renew lease when this fraction remains.
        graceful_shutdown_timeout: Seconds to wait for tasks during shutdown.
    """
    worker_id: str = ""
    queue_names: List[str] = field(default_factory=lambda: ["default"])
    task_types: Optional[List[str]] = None
    tenant_id: Optional[str] = None
    lease_seconds: float = 120.0
    lease_renewal_interval: float = 30.0
    heartbeat_interval: float = 10.0
    poll_interval: float = 1.0
    max_concurrent_tasks: int = 1
    lease_renewal_threshold: float = 0.3
    graceful_shutdown_timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.worker_id:
            self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"


# ============================================================
#  TASK HANDLER TYPE
# ============================================================

TaskHandler = Callable[[Dict[str, Any]], Any]
