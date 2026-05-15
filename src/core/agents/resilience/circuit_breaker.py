"""
Per-Agent Circuit Breaker for v18 architecture.

State Machine:
    CLOSED → OPEN:      failure_threshold consecutive failures
    OPEN → HALF_OPEN:   recovery_timeout elapsed
    HALF_OPEN → CLOSED: success_threshold consecutive successes
    HALF_OPEN → OPEN:   Any failure in half-open

When OPEN: All calls return deterministic fallback immediately.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Optional


__all__ = [
    "AgentCircuitBreaker",
    "CircuitBreakerManager",
    "CircuitState",
]


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class AgentCircuitBreaker:
    """Circuit breaker instance for a single agent."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

        # Stats
        self._total_rejected = 0
        self._total_successes = 0
        self._total_failures = 0
        self._state_transitions = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_rejected": self._total_rejected,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "state_transitions": self._state_transitions,
            }

    def can_call(self) -> bool:
        """Check if a call is allowed."""
        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            else:  # OPEN
                self._total_rejected += 1
                return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._total_successes += 1
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._total_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        """Force circuit to CLOSED state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)

    def _maybe_transition_to_half_open(self) -> None:
        """Check if OPEN circuit should transition to HALF_OPEN."""
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time is not None
            and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout
        ):
            self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state, resetting counters."""
        if self._state != new_state:
            self._state = new_state
            self._state_transitions += 1
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            if new_state == CircuitState.CLOSED:
                self._last_failure_time = None


class CircuitBreakerManager:
    """Manages per-agent circuit breaker instances."""

    # Default configs per agent group
    DEFAULT_CONFIGS = {
        "understanding": {"failure_threshold": 3, "recovery_timeout": 60.0},
        "memory": {"failure_threshold": 5, "recovery_timeout": 30.0},
        "business": {"failure_threshold": 3, "recovery_timeout": 60.0},
        "code": {"failure_threshold": 3, "recovery_timeout": 60.0},
        "validation": {"failure_threshold": 5, "recovery_timeout": 30.0},
        "automation": {"failure_threshold": 3, "recovery_timeout": 30.0},
        "reasoning": {"failure_threshold": 3, "recovery_timeout": 60.0},
        "verdict": {"failure_threshold": 3, "recovery_timeout": 60.0},
        "infrastructure": {"failure_threshold": 5, "recovery_timeout": 30.0},
    }

    def __init__(self) -> None:
        self._breakers: dict[str, AgentCircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_breaker(self, agent_name: str) -> AgentCircuitBreaker:
        """Get or create circuit breaker for an agent."""
        with self._lock:
            if agent_name not in self._breakers:
                group = self._classify_agent(agent_name)
                config = self.DEFAULT_CONFIGS.get(group, {"failure_threshold": 3, "recovery_timeout": 60.0})
                self._breakers[agent_name] = AgentCircuitBreaker(
                    name=agent_name, **config
                )
            return self._breakers[agent_name]

    def can_call(self, agent_name: str) -> bool:
        """Check if agent is allowed to make a call."""
        return self.get_breaker(agent_name).can_call()

    def record_success(self, agent_name: str) -> None:
        self.get_breaker(agent_name).record_success()

    def record_failure(self, agent_name: str) -> None:
        self.get_breaker(agent_name).record_failure()

    def reset(self, agent_name: str) -> None:
        self.get_breaker(agent_name).reset()

    def reset_all(self) -> None:
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()

    def all_stats(self) -> dict[str, dict]:
        with self._lock:
            return {name: b.stats for name, b in self._breakers.items()}

    def _classify_agent(self, name: str) -> str:
        """Classify agent into a group for default config."""
        name_lower = name.lower()
        if any(k in name_lower for k in ["intent", "entity", "target", "criticality", "bilingual"]):
            return "understanding"
        elif any(k in name_lower for k in ["memory", "relevance", "compressor", "prefetch"]):
            return "memory"
        elif any(k in name_lower for k in ["invoice", "inventory", "crm", "task", "report", "notification", "analytics", "router"]):
            return "business"
        elif any(k in name_lower for k in ["code_gen", "refactor", "optim", "fixer", "scaffold", "defensive"]):
            return "code"
        elif any(k in name_lower for k in ["security", "syntax", "chain", "config_valid", "risk", "fix_suggest"]):
            return "validation"
        elif any(k in name_lower for k in ["trigger", "action_inf", "schedule", "condition", "namer", "workflow"]):
            return "automation"
        elif any(k in name_lower for k in ["problem", "step", "template_r", "confidence", "conclusion"]):
            return "reasoning"
        elif any(k in name_lower for k in ["verdict", "evidence", "consensus", "pipeline"]):
            return "verdict"
        else:
            return "infrastructure"
