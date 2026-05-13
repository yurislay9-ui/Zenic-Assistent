"""
A47 CircuitBreakerManagerAgent — SINGLE RESPONSIBILITY: Manage circuit breakers per agent.

Wraps CircuitBreakerManager as a BaseAgent so it can participate in the
agent pipeline. Provides check, record, reset, and stats operations.

Ported from:
  - resilience/circuit_breaker.py (CircuitBreakerManager, AgentCircuitBreaker)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..resilience import BaseAgent, CircuitBreakerManager, CircuitState
from ..schemas import AgentResult


class CircuitBreakerManagerAgent(BaseAgent[AgentResult]):
    """
    A47: Manage circuit breakers per agent.

    Single Responsibility: Circuit breaker management ONLY.
    Method: Check state, record outcomes, reset breakers, get stats.
    Fallback: Return CLOSED state (assume available when no data).
    """

    def __init__(
        self,
        circuit_breaker_manager: Optional[CircuitBreakerManager] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            name="A47_CircuitBreakerManager",
            circuit_breaker_manager=circuit_breaker_manager,
            **kwargs,
        )

    def execute(self, input_data: Any) -> AgentResult:
        """
        Execute circuit breaker action.

        input_data must be a dict with:
          - 'action': "check" | "record_success" | "record_failure" | "reset" | "reset_all" | "stats" | "state"
          - 'agent_name': str (required for most actions)
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        action = input_data.get("action", "stats")
        agent_name = input_data.get("agent_name", "")

        if action == "check":
            return self._check(agent_name)
        elif action == "record_success":
            return self._record_success(agent_name)
        elif action == "record_failure":
            return self._record_failure(agent_name)
        elif action == "reset":
            return self._reset(agent_name)
        elif action == "reset_all":
            return self._reset_all()
        elif action == "stats":
            return self._stats(agent_name)
        elif action == "state":
            return self._state(agent_name)
        else:
            return AgentResult(
                success=False,
                source="error",
                error=f"Unknown circuit breaker action: {action}",
            )

    def _check(self, agent_name: str) -> AgentResult:
        """Check if agent can make a call."""
        if not agent_name:
            return AgentResult(success=False, source="error", error="agent_name required")

        can_call = self._cb_manager.can_call(agent_name)
        return AgentResult(
            success=True,
            data={"can_call": can_call, "agent_name": agent_name},
            source="deterministic",
        )

    def _record_success(self, agent_name: str) -> AgentResult:
        """Record a successful call."""
        if not agent_name:
            return AgentResult(success=False, source="error", error="agent_name required")

        self._cb_manager.record_success(agent_name)
        return AgentResult(success=True, source="deterministic")

    def _record_failure(self, agent_name: str) -> AgentResult:
        """Record a failed call."""
        if not agent_name:
            return AgentResult(success=False, source="error", error="agent_name required")

        self._cb_manager.record_failure(agent_name)
        return AgentResult(success=True, source="deterministic")

    def _reset(self, agent_name: str) -> AgentResult:
        """Reset circuit breaker for an agent."""
        if not agent_name:
            return AgentResult(success=False, source="error", error="agent_name required")

        self._cb_manager.reset(agent_name)
        return AgentResult(success=True, source="deterministic")

    def _reset_all(self) -> AgentResult:
        """Reset all circuit breakers."""
        self._cb_manager.reset_all()
        return AgentResult(success=True, source="deterministic")

    def _stats(self, agent_name: str) -> AgentResult:
        """Get circuit breaker stats."""
        if agent_name:
            breaker = self._cb_manager.get_breaker(agent_name)
            return AgentResult(
                success=True,
                data=breaker.stats,
                source="deterministic",
            )
        else:
            return AgentResult(
                success=True,
                data=self._cb_manager.all_stats(),
                source="deterministic",
            )

    def _state(self, agent_name: str) -> AgentResult:
        """Get circuit breaker state for an agent."""
        if not agent_name:
            return AgentResult(success=False, source="error", error="agent_name required")

        breaker = self._cb_manager.get_breaker(agent_name)
        state = breaker.state

        return AgentResult(
            success=True,
            data={"state": state.value, "agent_name": agent_name},
            source="deterministic",
        )

    # ──────────────────────────────────────────────────────────
    # CONVENIENCE METHODS (for direct use by other agents)
    # ──────────────────────────────────────────────────────────

    def can_call(self, agent_name: str) -> bool:
        """Quick check: can this agent make a call?"""
        return self._cb_manager.can_call(agent_name)

    def get_breaker_state(self, agent_name: str) -> str:
        """Get the circuit breaker state as string."""
        return self._cb_manager.get_breaker(agent_name).state.value

    def record_success(self, agent_name: str) -> None:
        """Record success directly."""
        self._cb_manager.record_success(agent_name)

    def record_failure(self, agent_name: str) -> None:
        """Record failure directly."""
        self._cb_manager.record_failure(agent_name)

    def reset(self, agent_name: str) -> None:
        """Reset breaker directly."""
        self._cb_manager.reset(agent_name)

    def fallback(self, input_data: Any) -> AgentResult:
        """Fallback: Assume CLOSED (available) when no data."""
        return AgentResult(
            success=True,
            data={"can_call": True, "state": "CLOSED"},
            source="fallback",
        )
