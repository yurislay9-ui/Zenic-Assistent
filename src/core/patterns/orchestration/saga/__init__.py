"""ZENIC-AGENTS - Saga Pattern (Multi-Step Rollback)."""
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from ._types import SagaStatus, SagaStep, SagaContext
from ._sync_mixin import SagaSyncMixin
from ._async_mixin import SagaAsyncMixin

logger = logging.getLogger("zenic_agents.patterns.orchestration.saga")

__all__ = ["SagaStatus", "SagaStep", "SagaContext", "Saga"]


class Saga(SagaSyncMixin, SagaAsyncMixin):
    """Orchestrator for multi-step operations with automatic rollback."""

    def __init__(self, name: str, steps: List[SagaStep]) -> None:
        if not name:
            raise ValueError("Saga name must not be empty")
        if not steps:
            raise ValueError("Saga must have at least one step")

        self._name: str = name
        self._steps: List[SagaStep] = list(steps)
        self._status: SagaStatus = SagaStatus.PENDING
        self._lock = threading.Lock()
        self._saga_id: str = str(uuid.uuid4())

        # Stats
        self._execution_count: int = 0
        self._compensation_count: int = 0
        self._error_count: int = 0
        self._last_execution_time_ms: float = 0.0

    @property
    def status(self) -> SagaStatus:
        """Current lifecycle status of the saga."""
        return self._status

    @property
    def name(self) -> str:
        """Human-readable saga name."""
        return self._name

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics for monitoring and debugging."""
        with self._lock:
            return {
                "name": self._name,
                "saga_id": self._saga_id,
                "status": self._status.value,
                "step_count": len(self._steps),
                "execution_count": self._execution_count,
                "compensation_count": self._compensation_count,
                "error_count": self._error_count,
                "last_execution_time_ms": self._last_execution_time_ms,
            }
