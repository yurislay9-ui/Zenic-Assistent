"""
ZENIC-AGENTS - Circuit Breaker Pattern v16

Thread-safe Circuit Breaker for resilient fault tolerance.
Designed for Android/Termux (500MB RAM) — stdlib only.

State machine:
    CLOSED  → OPEN       (failure_threshold reached)
    OPEN    → HALF_OPEN  (recovery_timeout elapsed)
    HALF_OPEN → CLOSED   (success_threshold reached in half-open)
    HALF_OPEN → OPEN     (any failure in half-open)
"""

import threading
import time
import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["CircuitBreaker", "CircuitState", "CircuitOpenError"]


# ============================================================
#  ENUMS
# ============================================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ============================================================
#  EXCEPTIONS
# ============================================================

class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is open."""

    def __init__(self, name: str, remaining_timeout: float = 0.0):
        self.circuit_name = name
        self.remaining_timeout = remaining_timeout
        super().__init__(
            f"Circuit '{name}' is OPEN. "
            f"Retry after {remaining_timeout:.1f}s."
        )


# ============================================================
#  CIRCUIT BREAKER
# ============================================================

class CircuitBreaker:
    """
    Thread-safe Circuit Breaker with CLOSED → OPEN → HALF_OPEN state machine.

    Parameters:
        name: Human-readable identifier for this breaker.
        failure_threshold: Consecutive failures before tripping to OPEN.
        recovery_timeout: Seconds in OPEN before transitioning to HALF_OPEN.
        half_open_max_calls: Max calls allowed in HALF_OPEN before deciding.
        success_threshold: Consecutive successes in HALF_OPEN to close circuit.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 3,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout < 0:
            raise ValueError("recovery_timeout must be >= 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")
        if success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")

        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold

        # State
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_call_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None

        # Cumulative stats
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0

        self._lock = threading.Lock()

    # ----------------------------------------------------------
    #  Properties
    # ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Identifier for this circuit breaker."""
        return self._name

    @property
    def state(self) -> CircuitState:
        """
        Current state, lazily transitioning OPEN → HALF_OPEN when
        recovery_timeout has elapsed.
        """
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def stats(self) -> Dict[str, Any]:
        """Snapshot of circuit breaker statistics."""
        with self._lock:
            self._maybe_transition_to_half_open()
            remaining = 0.0
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            return {
                "name": self._name,
                "current_state": self._state.value,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "consecutive_failures": self._failure_count,
                "consecutive_successes": self._success_count,
                "half_open_call_count": self._half_open_call_count,
                "last_failure_time": self._last_failure_time,
                "remaining_timeout": remaining,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout": self._recovery_timeout,
                "success_threshold": self._success_threshold,
            }

    # ----------------------------------------------------------
    #  Public API — recording
    # ----------------------------------------------------------

    def record_success(self) -> None:
        """Record a successful call and potentially close the circuit."""
        with self._lock:
            self._total_calls += 1
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_call_count += 1
                if self._success_count >= self._success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        "Circuit '%s': HALF_OPEN → CLOSED "
                        "(%d consecutive successes)",
                        self._name, self._success_count,
                    )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0
                self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed call and potentially open the circuit."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._failure_count += 1
            self._success_count = 0
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_call_count += 1
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    "Circuit '%s': HALF_OPEN → OPEN (failure in half-open)",
                    self._name,
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        "Circuit '%s': CLOSED → OPEN "
                        "(%d consecutive failures)",
                        self._name, self._failure_count,
                    )

    # ----------------------------------------------------------
    #  Public API — call through breaker
    # ----------------------------------------------------------

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute *func* synchronously through the circuit breaker.

        Raises:
            CircuitOpenError: If the circuit is OPEN.
        """
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                remaining = 0.0
                if self._opened_at is not None:
                    elapsed = time.monotonic() - self._opened_at
                    remaining = max(0.0, self._recovery_timeout - elapsed)
                raise CircuitOpenError(self._name, remaining)
            if (
                self._state == CircuitState.HALF_OPEN
                and self._half_open_call_count >= self._half_open_max_calls
            ):
                raise CircuitOpenError(self._name, 0.0)

        # Execute outside the lock to avoid blocking other threads
        try:
            result = func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result

    async def call_async(
        self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """
        Execute *coro_func* asynchronously through the circuit breaker.

        Raises:
            CircuitOpenError: If the circuit is OPEN.
        """
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                remaining = 0.0
                if self._opened_at is not None:
                    elapsed = time.monotonic() - self._opened_at
                    remaining = max(0.0, self._recovery_timeout - elapsed)
                raise CircuitOpenError(self._name, remaining)
            if (
                self._state == CircuitState.HALF_OPEN
                and self._half_open_call_count >= self._half_open_max_calls
            ):
                raise CircuitOpenError(self._name, 0.0)

        try:
            result = await coro_func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result

    # ----------------------------------------------------------
    #  Public API — manual control
    # ----------------------------------------------------------

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state, clearing all counters."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            logger.info("Circuit '%s': reset to CLOSED", self._name)

    def force_open(self) -> None:
        """Force the circuit into OPEN state."""
        with self._lock:
            self._transition_to(CircuitState.OPEN)
            logger.info("Circuit '%s': forced OPEN", self._name)

    def force_close(self) -> None:
        """Force the circuit into CLOSED state (does not reset stats)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_call_count = 0
            self._opened_at = None
            logger.info("Circuit '%s': forced CLOSED", self._name)

    # ----------------------------------------------------------
    #  Internal helpers
    # ----------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """
        Check if enough time has elapsed in OPEN to transition to HALF_OPEN.
        Must be called while holding ``self._lock``.
        """
        if self._state != CircuitState.OPEN:
            return
        if self._opened_at is None:
            return
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self._recovery_timeout:
            self._transition_to(CircuitState.HALF_OPEN)
            logger.info(
                "Circuit '%s': OPEN → HALF_OPEN (recovery timeout elapsed)",
                self._name,
            )

    def _transition_to(self, new_state: CircuitState) -> None:
        """
        Perform state transition and reset relevant counters.
        Must be called while holding ``self._lock``.
        """
        self._state = new_state

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_call_count = 0
            self._opened_at = None

        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            self._half_open_call_count = 0
            self._opened_at = time.monotonic()

        elif new_state == CircuitState.HALF_OPEN:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_call_count = 0

    # ----------------------------------------------------------
    #  Dunder helpers
    # ----------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self._name!r}, "
            f"state={self._state.value!r})"
        )
