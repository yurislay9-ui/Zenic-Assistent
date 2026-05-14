"""
ZENIC-AGENTS - Saga Pattern (Multi-Step Rollback)

Formal SAGA pattern implementation for distributed multi-step operations
with automatic compensation on failure.

When a step fails, all previously completed steps are compensated in
reverse order. This is critical for the ZENIC pipeline where operations
like AST surgery, code generation, and file writes must be rolled back
if a downstream step fails.

Features:
- Sequential step execution with automatic compensation on failure
- Reverse-order compensation for completed steps
- Per-step timeout support
- Shared context for inter-step communication
- Sync and async execution
- Thread-safe
- Detailed logging at each step/compensation boundary
- Status tracking (PENDING -> RUNNING -> COMPLETED/COMPENSATING/FAILED)

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import asyncio
import enum
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("zenic_agents.patterns.orchestration.saga")

__all__ = [
    "SagaStatus",
    "SagaStep",
    "SagaContext",
    "Saga",
]


# ============================================================
#  SAGA STATUS
# ============================================================

class SagaStatus(str, enum.Enum):
    """
    Lifecycle states of a Saga execution.

    State transitions:
        PENDING -> RUNNING -> COMPLETED
                          |-> COMPENSATING -> COMPENSATED
                                            |-> FAILED
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


# ============================================================
#  SAGA STEP
# ============================================================

@dataclass
class SagaStep:
    """
    A single step in a Saga with optional compensation.

    Attributes:
        name: Human-readable step name for logging.
        action: Callable that executes the step. Receives SagaContext
                as its only argument. May return a value that is
                stored in context.results[name].
        compensation: Optional callable to undo the step's effects.
                     Receives SagaContext as its only argument.
                     Called in reverse order if a subsequent step fails.
        timeout: Optional timeout in seconds. If the step (action or
                compensation) exceeds this duration, it is considered
                failed.
    """
    name: str
    action: Callable[[Any], Any]
    compensation: Optional[Callable[[Any], Any]] = None
    timeout: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SagaStep name must not be empty")
        if self.action is None:
            raise ValueError("SagaStep action must not be None")


# ============================================================
#  SAGA CONTEXT
# ============================================================

class SagaContext:
    """
    Shared mutable context passed through all saga steps.

    Provides a dict-like interface for inter-step communication,
    plus dedicated storage for step results and accumulated errors.

    Attributes:
        saga_id: Unique identifier for the saga execution.
        results: Dict mapping step names to their return values.
        errors: List of error messages accumulated during execution.

    Usage::

        ctx = SagaContext(saga_id="order-123", steps=[...])
        ctx.set("user_id", 42)
        user_id = ctx.get("user_id")  # 42
        ctx.has("user_id")  # True
    """

    def __init__(self, saga_id: str, steps: Optional[List[SagaStep]] = None) -> None:
        if not saga_id:
            raise ValueError("saga_id must not be empty")

        self.saga_id: str = saga_id
        self._state: Dict[str, Any] = {}
        self.results: Dict[str, Any] = {}
        self.errors: List[str] = []
        self._steps: List[SagaStep] = steps or []
        self._completed_steps: List[SagaStep] = []

    def set(self, key: str, value: Any) -> None:
        """
        Store a value in the shared context.

        Args:
            key: Context key.
            value: Value to store.
        """
        self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the shared context.

        Args:
            key: Context key.
            default: Value to return if key is not found.

        Returns:
            The stored value, or default if not found.
        """
        return self._state.get(key, default)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the shared context.

        Args:
            key: Context key to check.

        Returns:
            True if the key exists.
        """
        return key in self._state

    @property
    def state(self) -> Dict[str, Any]:
        """Read-only snapshot of the current context state."""
        return dict(self._state)

    def mark_step_completed(self, step: SagaStep) -> None:
        """
        Record that a step has completed successfully.

        Completed steps are tracked for compensation in reverse order.

        Args:
            step: The completed SagaStep.
        """
        self._completed_steps.append(step)

    @property
    def completed_steps(self) -> List[SagaStep]:
        """
        Steps that completed successfully, in execution order.

        During compensation, these are reversed.
        """
        return list(self._completed_steps)

    def add_error(self, error: str) -> None:
        """
        Append an error message to the accumulated errors list.

        Args:
            error: Error message string.
        """
        self.errors.append(error)

