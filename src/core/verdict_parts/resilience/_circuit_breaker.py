"""Verdict Resilience - Circuit Breaker & Retry Config."""

import logging
import time
import random
from typing import Any, Dict, Optional

logger = logging.getLogger("zenic_agents.verdict_parts.resilience")


class VerdictCircuitBreaker:
    """
    Circuit Breaker específico para llamadas de veredicto al LLM.

    Protege contra:
      - LLM que tarda demasiado (timeouts repetidos)
      - LLM que devuelve respuestas ambiguas repetidamente
      - LLM que está completamente caído

    Estado CLOSED: Todo normal, el LLM se llama cuando hay empate.
    Estado OPEN: El LLM no se llama, todos los veredictos son fallback NO.
    Estado HALF_OPEN: Se permite 1 llamada de prueba para ver si el LLM se recuperó.

    Thread-safe. Optimizado para baja memoria.
    """

    def __init__(
        self,
        name: str = "verdict_llm",
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        success_threshold: int = 2,
    ):
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold

        self._state = VerdictCircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._opened_at: Optional[float] = None
        self._last_failure_time: Optional[float] = None

        # Stats
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_rejected = 0  # Calls rejected because circuit was OPEN

        self._lock = threading.Lock()

    @property
    def state(self) -> VerdictCircuitState:
        """Current state with lazy OPEN → HALF_OPEN transition."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def is_open(self) -> bool:
        """True if the circuit is OPEN (LLM calls are rejected)."""
        return self.state == VerdictCircuitState.OPEN

    @property
    def stats(self) -> Dict[str, Any]:
        """Snapshot of circuit breaker statistics."""
        with self._lock:
            self._maybe_transition_to_half_open()
            remaining = 0.0
            if self._state == VerdictCircuitState.OPEN and self._opened_at:
                elapsed = time.monotonic() - self._opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            return {
                "name": self._name,
                "state": self._state.value,
                "failure_threshold": self._failure_threshold,
                "consecutive_failures": self._failure_count,
                "consecutive_successes": self._success_count,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "remaining_timeout": remaining,
                "recovery_timeout": self._recovery_timeout,
            }

    def can_call(self) -> bool:
        """Check if a call to the LLM is allowed."""
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == VerdictCircuitState.CLOSED:
                return True
            if self._state == VerdictCircuitState.HALF_OPEN:
                return self._half_open_calls < self._half_open_max_calls
            # OPEN
            self._total_rejected += 1
            return False

    def record_success(self) -> None:
        """Record a successful LLM call."""
        with self._lock:
            self._total_calls += 1
            self._total_successes += 1

            if self._state == VerdictCircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls += 1
                if self._success_count >= self._success_threshold:
                    self._transition_to(VerdictCircuitState.CLOSED)
                    logger.info(
                        f"VerdictCircuitBreaker[{self._name}]: "
                        f"HALF_OPEN → CLOSED ({self._success_count} successes)"
                    )
            elif self._state == VerdictCircuitState.CLOSED:
                self._failure_count = 0
                self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed LLM call."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._failure_count += 1
            self._success_count = 0
            self._last_failure_time = time.monotonic()

            if self._state == VerdictCircuitState.HALF_OPEN:
                self._half_open_calls += 1
                self._transition_to(VerdictCircuitState.OPEN)
                logger.warning(
                    f"VerdictCircuitBreaker[{self._name}]: "
                    f"HALF_OPEN → OPEN (failure in half-open)"
                )
            elif self._state == VerdictCircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition_to(VerdictCircuitState.OPEN)
                    logger.warning(
                        f"VerdictCircuitBreaker[{self._name}]: "
                        f"CLOSED → OPEN ({self._failure_count} consecutive failures)"
                    )

    def reset(self) -> None:
        """Reset to CLOSED state."""
        with self._lock:
            self._transition_to(VerdictCircuitState.CLOSED)
            logger.info(f"VerdictCircuitBreaker[{self._name}]: Reset to CLOSED")

    def _maybe_transition_to_half_open(self) -> None:
        """Check if recovery_timeout has elapsed in OPEN state."""
        if self._state != VerdictCircuitState.OPEN or self._opened_at is None:
            return
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self._recovery_timeout:
            self._transition_to(VerdictCircuitState.HALF_OPEN)
            logger.info(
                f"VerdictCircuitBreaker[{self._name}]: "
                f"OPEN → HALF_OPEN (recovery timeout elapsed)"
            )

    def _transition_to(self, new_state: VerdictCircuitState) -> None:
        """Perform state transition."""
        self._state = new_state
        if new_state == VerdictCircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._opened_at = None
        elif new_state == VerdictCircuitState.OPEN:
            self._success_count = 0
            self._half_open_calls = 0
            self._opened_at = time.monotonic()
        elif new_state == VerdictCircuitState.HALF_OPEN:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0


# ============================================================
#  VERDICT RETRY POLICY
# ============================================================

@dataclass
class VerdictRetryConfig:
    """
    Configuration for verdict retry with exponential backoff.

    Attributes:
        max_attempts: Maximum LLM call attempts (default 3).
        base_delay: Base delay in seconds between retries.
        max_delay: Upper bound for delay.
        exponential_base: Base for exponential calculation.
        jitter: Whether to add random jitter.
        jitter_max: Jitter multiplier (0..1).
        timeout_per_attempt: Timeout in seconds per individual LLM call.
    """
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 0.3
    timeout_per_attempt: float = 5.0

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for the given attempt (1-based)."""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter and delay > 0:
            delay += random.uniform(0, self.jitter_max * delay)
        return delay


# ============================================================
#  VERDICT HEALTH MONITOR
# ============================================================

@dataclass
class VerdictHealthSnapshot:
    """Snapshot of the LLM health at a point in time."""
    is_healthy: bool
    avg_latency_s: float
    success_rate: float
    total_calls: int
    total_failures: int
    total_timeouts: int
    total_ambiguous: int
    last_call_time: Optional[float]
    circuit_breaker_state: str


