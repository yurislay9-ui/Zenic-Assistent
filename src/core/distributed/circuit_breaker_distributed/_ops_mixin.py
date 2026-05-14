"""
Distributed Circuit Breaker — Core Operations Mixin.

Contains the record operations, call methods, manual control,
and state synchronization methods for DistributedCircuitBreaker.
"""

import logging
import threading
import time
from typing import Any, Callable

from src.core.patterns.resilience.circuit_breaker import (
    CircuitState,
    CircuitOpenError,
)

logger = logging.getLogger(__name__)


class BreakerOpsMixin:
    """Mixin providing core distributed circuit breaker operations.

    Expects the host class to provide:
      - _local_state: SharedCircuitState
      - _local_breaker: CircuitBreaker (local fallback)
      - _lock: threading.Lock
      - _name: str
      - _failure_threshold: int
      - _recovery_timeout: float
      - _half_open_max_calls: int
      - _success_threshold: int
      - _backend: CoordinationBackend
      - _total_syncs: int
      - _sync_errors: int
      - _sync_interval: float
      - _last_sync: float
      - state (property): CircuitState
      - _maybe_sync(): method
      - _persist_state(): method
    """

    # ----------------------------------------------------------
    #  RECORD OPERATIONS
    # ----------------------------------------------------------

    def record_success(self) -> None:
        """
        Record a successful call and potentially close the circuit.

        Updates both local state and persisted shared state.
        """
        with self._lock:
            state = self._local_state
            if state.state == "half_open":
                state.success_count += 1
                state.half_open_call_count += 1
                if state.success_count >= self._success_threshold:
                    state.state = "closed"
                    state.failure_count = 0
                    state.success_count = 0
                    state.half_open_call_count = 0
                    state.opened_at = None
                    logger.info(
                        "DistCircuit '%s': HALF_OPEN -> CLOSED "
                        "(%d successes)",
                        self._name, state.success_count,
                    )
            elif state.state == "closed":
                state.failure_count = 0
                state.success_count += 1

        # Also update local fallback
        self._local_breaker.record_success()

        # Persist to backend
        self._persist_state()

    def record_failure(self) -> None:
        """
        Record a failed call and potentially open the circuit.

        Updates both local state and persisted shared state.
        """
        with self._lock:
            state = self._local_state
            state.failure_count += 1
            state.success_count = 0

            if state.state == "half_open":
                state.half_open_call_count += 1
                state.state = "open"
                state.opened_at = time.monotonic()
                logger.warning(
                    "DistCircuit '%s': HALF_OPEN -> OPEN (failure in half-open)",
                    self._name,
                )
            elif state.state == "closed":
                if state.failure_count >= self._failure_threshold:
                    state.state = "open"
                    state.opened_at = time.monotonic()
                    logger.warning(
                        "DistCircuit '%s': CLOSED -> OPEN "
                        "(%d consecutive failures)",
                        self._name, state.failure_count,
                    )

        # Also update local fallback
        self._local_breaker.record_failure()

        # Persist to backend
        self._persist_state()

    # ----------------------------------------------------------
    #  CALL THROUGH BREAKER
    # ----------------------------------------------------------

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute func through the distributed circuit breaker.

        Checks shared state from backend (with local cache) before
        allowing the call. Falls back to local breaker if backend
        is unavailable.

        Args:
            func: The callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The result of func(*args, **kwargs).

        Raises:
            CircuitOpenError: If the circuit is OPEN.
        """
        # Check state (may sync from backend)
        current_state = self.state

        if current_state == CircuitState.OPEN:
            remaining = 0.0
            if self._local_state.opened_at is not None:
                elapsed = time.monotonic() - self._local_state.opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            raise CircuitOpenError(self._name, remaining)

        if (
            current_state == CircuitState.HALF_OPEN
            and self._local_state.half_open_call_count >= self._half_open_max_calls
        ):
            raise CircuitOpenError(self._name, 0.0)

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
        Execute an async function through the distributed circuit breaker.

        Same semantics as call() but supports async callables.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            remaining = 0.0
            if self._local_state.opened_at is not None:
                elapsed = time.monotonic() - self._local_state.opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            raise CircuitOpenError(self._name, remaining)

        if (
            current_state == CircuitState.HALF_OPEN
            and self._local_state.half_open_call_count >= self._half_open_max_calls
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
    #  MANUAL CONTROL
    # ----------------------------------------------------------

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._local_state.state = "closed"
            self._local_state.failure_count = 0
            self._local_state.success_count = 0
            self._local_state.half_open_call_count = 0
            self._local_state.opened_at = None
        self._local_breaker.reset()
        self._persist_state()
        logger.info("DistCircuit '%s': Reset to CLOSED", self._name)

    def force_open(self) -> None:
        """Force the circuit into OPEN state."""
        with self._lock:
            self._local_state.state = "open"
            self._local_state.opened_at = time.monotonic()
        self._local_breaker.force_open()
        self._persist_state()
        logger.info("DistCircuit '%s': Forced OPEN", self._name)

    def force_close(self) -> None:
        """Force the circuit into CLOSED state."""
        with self._lock:
            self._local_state.state = "closed"
            self._local_state.failure_count = 0
            self._local_state.success_count = 0
            self._local_state.half_open_call_count = 0
            self._local_state.opened_at = None
        self._local_breaker.force_close()
        self._persist_state()
        logger.info("DistCircuit '%s': Forced CLOSED", self._name)

    # ----------------------------------------------------------
    #  STATE SYNC
    # ----------------------------------------------------------

    def _maybe_sync(self) -> None:
        """
        Sync local state from backend if the sync interval has elapsed.

        Handles the OPEN -> HALF_OPEN transition based on recovery_timeout.
        """
        from ._state import SharedCircuitState

        now = time.time()
        if now - self._last_sync < self._sync_interval:
            return

        with self._lock:
            if now - self._last_sync < self._sync_interval:
                return  # Another thread synced while we waited
            self._last_sync = now

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                remote_state = loop.run_until_complete(
                    self._backend.get_circuit_state(self._name)
                )
            finally:
                loop.close()

            if remote_state is not None:
                version = remote_state.pop("version", 0)
                with self._lock:
                    # Only update if remote is newer
                    if version >= self._local_state.version:
                        self._local_state = SharedCircuitState.from_dict(
                            remote_state, version=version,
                        )

                        # Check OPEN -> HALF_OPEN transition
                        if self._local_state.state == "open":
                            if self._local_state.opened_at is not None:
                                elapsed = time.monotonic() - self._local_state.opened_at
                                if elapsed >= self._recovery_timeout:
                                    self._local_state.state = "half_open"
                                    self._local_state.failure_count = 0
                                    self._local_state.success_count = 0
                                    self._local_state.half_open_call_count = 0
                                    logger.info(
                                        "DistCircuit '%s': OPEN -> HALF_OPEN "
                                        "(recovery timeout elapsed)",
                                        self._name,
                                    )

                self._total_syncs += 1

        except Exception as exc:
            self._sync_errors += 1
            logger.debug(
                "DistCircuit '%s': Sync failed, using local state: %s",
                self._name, exc,
            )

    def _persist_state(self) -> None:
        """Persist current local state to the backend."""
        with self._lock:
            state_dict = self._local_state.to_dict()
            version = self._local_state.version

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._backend.update_circuit_state(
                        self._name,
                        state_dict,
                        expected_version=version if version > 0 else None,
                    )
                )
            finally:
                loop.close()
        except Exception as exc:
            logger.debug(
                "DistCircuit '%s': Persist failed: %s", self._name, exc,
            )
