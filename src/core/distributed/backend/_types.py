"""CoordinationBackend - Types and configuration."""

import enum
import uuid
from dataclasses import dataclass, field
from typing import Optional

from src.core.patterns.resilience.retry import RetryConfig


# ============================================================
#  ENUMS
# ============================================================

class BackendType(str, enum.Enum):
    """Supported coordination backend types."""
    POSTGRESQL = "postgresql"
    MEMORY = "memory"


# ============================================================
#  CONFIGURATION
# ============================================================

@dataclass
class BackendConfig:
    """
    Configuration for the coordination backend.

    Attributes:
        backend_type: Which backend to use (postgresql or memory).
        connection_string: Database connection string (for PostgreSQL).
        pool_min: Minimum connection pool size.
        pool_max: Maximum connection pool size.
        connect_timeout: Connection timeout in seconds.
        statement_timeout: SQL statement timeout in milliseconds.
        heartbeat_interval: How often heartbeats are sent (seconds).
        lease_duration: Default task lease duration (seconds).
        node_id: Unique identifier for this node. Auto-generated if empty.
        retry_config: Retry configuration for backend operations.
    """
    backend_type: BackendType = BackendType.MEMORY
    connection_string: str = ""
    pool_min: int = 2
    pool_max: int = 10
    connect_timeout: float = 5.0
    statement_timeout: int = 5000
    heartbeat_interval: float = 10.0
    lease_duration: float = 120.0
    node_id: str = ""
    retry_config: RetryConfig = field(default_factory=lambda: RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        backoff_strategy="exponential",
        jitter=True,
        retryable_exceptions=(Exception,),
    ))

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"node-{uuid.uuid4().hex[:8]}"
