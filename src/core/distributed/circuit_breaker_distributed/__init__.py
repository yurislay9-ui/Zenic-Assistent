"""
ZENIC-AGENTS - Distributed Circuit Breaker

Circuit breaker with shared state across multiple nodes/processes.
Unlike the single-process CircuitBreaker in patterns/resilience/,
this implementation:

- Persists circuit state to the CoordinationBackend (PostgreSQL)
- Uses optimistic concurrency control (version-based CAS) for updates
- Allows all nodes to see the same circuit state
- Supports local caching with configurable sync interval
- Gracefully falls back to local-only mode if backend is unavailable

State Machine (same as single-process):
    CLOSED  -> OPEN       (failure_threshold reached)
    OPEN    -> HALF_OPEN  (recovery_timeout elapsed)
    HALF_OPEN -> CLOSED   (success_threshold reached)
    HALF_OPEN -> OPEN     (any failure in half-open)

Integration:
    Designed to be used as a drop-in replacement for the single-process
    CircuitBreaker in the FastAPI app and other components.
"""

import logging
import threading
import time
from typing import Any, Dict

from ..backend import CoordinationBackend
from src.core.patterns.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)

from ._state import SharedCircuitState
from ._ops_mixin import BreakerOpsMixin

logger = logging.getLogger(__name__)

__all__ = [
    "DistributedCircuitBreaker",
    "SharedCircuitState",
]


class DistributedCircuitBreaker(BreakerOpsMixin):
    """
    Circuit breaker with shared state across distributed nodes.

    Maintains local state for fast reads and periodically syncs
    with the CoordinationBackend. Writes (state transitions) are
    persisted immediately to ensure all nodes see consistent state.

    Falls back to a local CircuitBreaker if the backend is unavailable,
    ensuring graceful degradation in single-process or disconnected mode.

    Usage::

        breaker = DistributedCircuitBreaker(
            name="orchestrator",
            backend=backend,
            failure_threshold=5,
            recovery_timeout=30.0,
        )

        # Same API as single-process CircuitBreaker
        result = breaker.call(my_function, arg1, arg2)
    """

    # How often to sync local cache from backend (seconds)
    DEFAULT_SYNC_INTERVAL = 5.0

    def __init__(
        self,
        name: str,
        backend: CoordinationBackend,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 3,
        sync_interval: float = DEFAULT_SYNC_INTERVAL,
    ) -> None:
        """
        Initialize the distributed circuit breaker.

        Args:
            name: Circuit breaker name (unique per service).
            backend: Coordination backend for shared state.
            failure_threshold: Consecutive failures before OPEN.
            recovery_timeout: Seconds before OPEN -> HALF_OPEN.
            half_open_max_calls: Max calls in HALF_OPEN.
            success_threshold: Successes in HALF_OPEN to close.
            sync_interval: How often to sync from backend.
        """
        self._name = name
        self._backend = backend
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold
        self._sync_interval = sync_interval

        # Local fallback circuit breaker (used when backend is unavailable)
        self._local_breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            success_threshold=success_threshold,
        )

        # Local cache of shared state
        self._local_state = SharedCircuitState(name=name, state="closed")
        self._last_sync: float = 0.0
        self._lock = threading.Lock()

        # Stats
        self._total_syncs: int = 0
        self._sync_errors: int = 0

    # ----------------------------------------------------------
    #  PROPERTIES
    # ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Circuit breaker name."""
        return self._name

    @property
    def state(self) -> CircuitState:
        """
        Current circuit state, synced from backend if stale.

        Returns the locally-cached state, refreshing from the backend
        if the sync interval has elapsed.
        """
        self._maybe_sync()
        state_str = self._local_state.state
        try:
            return CircuitState(state_str)
        except ValueError:
            return CircuitState.CLOSED

    @property
    def stats(self) -> Dict[str, Any]:
        """Circuit breaker statistics."""
        self._maybe_sync()
        with self._lock:
            remaining = 0.0
            if (
                self._local_state.state == "open"
                and self._local_state.opened_at is not None
            ):
                elapsed = time.monotonic() - self._local_state.opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)

            return {
                "name": self._name,
                "current_state": self._local_state.state,
                "consecutive_failures": self._local_state.failure_count,
                "consecutive_successes": self._local_state.success_count,
                "half_open_call_count": self._local_state.half_open_call_count,
                "version": self._local_state.version,
                "total_syncs": self._total_syncs,
                "sync_errors": self._sync_errors,
                "remaining_timeout": remaining,
                "backend_type": type(self._backend).__name__,
            }

    def __repr__(self) -> str:
        return (
            f"DistributedCircuitBreaker(name={self._name!r}, "
            f"state={self._local_state.state!r}, "
            f"version={self._local_state.version})"
        )
