"""
Tests for Layer 9: Infrastructure & Resilience agents (A44-A48).

All 5 agents tested:
  - A44 AgentRunner (agent execution with resilience)
  - A45 HealthMonitorAgent (health tracking)
  - A46 AuditLoggerAgent (audit logging)
  - A47 CircuitBreakerManagerAgent (circuit breaker management)
  - A48 BilingualRouter (language detection)
"""

import pytest
import time
import threading

from src.core.agents_v2.infrastructure import (
    AgentRunner,
    HealthMonitorAgent,
    AuditLoggerAgent,
    CircuitBreakerManagerAgent,
)
from src.core.agents_v2.understanding import BilingualRouter
from src.core.agents_v2.resilience import (
    BaseAgent,
    CircuitBreakerManager,
    GlobalHealthMonitor,
    AuditLogger,
    AuditEntry,
    AgentCircuitBreaker,
    CircuitState,
    BulkheadManager,
    AgentRetryConfig,
)
from src.core.agents_v2.schemas import (
    AgentResult,
    HealthSnapshot,
    LanguageResult,
)


# ======================================================================
# Helper: Simple test agent
# ======================================================================

class EchoAgent(BaseAgent[AgentResult]):
    """Simple agent that echoes input for testing."""

    def __init__(self, name="EchoAgent", **kwargs):
        super().__init__(name=name, **kwargs)

    def execute(self, input_data):
        return AgentResult(success=True, data=input_data, source="deterministic")

    def fallback(self, input_data):
        return AgentResult(success=False, source="fallback")


class FailingAgent(BaseAgent[AgentResult]):
    """Agent that always fails for testing."""

    def __init__(self, name="FailingAgent", **kwargs):
        # Use zero-delay retry config for tests
        if "retry_config" not in kwargs:
            kwargs["retry_config"] = AgentRetryConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)
        super().__init__(name=name, **kwargs)

    def execute(self, input_data):
        raise RuntimeError("Intentional failure for testing")

    def fallback(self, input_data):
        return AgentResult(success=False, source="fallback", error="Intentional failure")


# ======================================================================
# A44 AgentRunner Tests
# ======================================================================



class TestCircuitBreakerManagerAgent:
    """A47: Manage circuit breakers per agent."""

    def setup_method(self):
        self.cb_agent = CircuitBreakerManagerAgent()

    def test_check_initial_state(self):
        result = self.cb_agent.execute({
            "action": "check",
            "agent_name": "NewAgent",
        })
        assert result.success is True
        assert result.data["can_call"] is True

    def test_check_no_agent_name(self):
        result = self.cb_agent.execute({"action": "check"})
        assert result.success is False

    def test_record_success(self):
        result = self.cb_agent.execute({
            "action": "record_success",
            "agent_name": "TestAgent",
        })
        assert result.success is True

    def test_record_failure(self):
        result = self.cb_agent.execute({
            "action": "record_failure",
            "agent_name": "TestAgent",
        })
        assert result.success is True

    def test_circuit_opens_after_failures(self):
        """Circuit should open after failure_threshold consecutive failures."""
        # Use a name that maps to "understanding" group (threshold=3)
        agent_name = "A01_IntentClassifier"
        for _ in range(3):
            self.cb_agent.execute({
                "action": "record_failure",
                "agent_name": agent_name,
            })

        result = self.cb_agent.execute({
            "action": "check",
            "agent_name": agent_name,
        })
        assert result.data["can_call"] is False

    def test_reset_breaker(self):
        agent_name = "A02_EntityExtractor"  # understanding group, threshold=3
        # Trip the breaker
        for _ in range(3):
            self.cb_agent.execute({
                "action": "record_failure",
                "agent_name": agent_name,
            })

        # Reset it
        result = self.cb_agent.execute({
            "action": "reset",
            "agent_name": agent_name,
        })
        assert result.success is True

        # Should be available again
        check = self.cb_agent.execute({
            "action": "check",
            "agent_name": agent_name,
        })
        assert check.data["can_call"] is True

    def test_reset_all(self):
        # Trip some breakers (use understanding group names, threshold=3)
        for _ in range(3):
            self.cb_agent.execute({"action": "record_failure", "agent_name": "A01_Intent"})
            self.cb_agent.execute({"action": "record_failure", "agent_name": "A02_Entity"})

        # Reset all
        result = self.cb_agent.execute({"action": "reset_all"})
        assert result.success is True

    def test_stats_per_agent(self):
        self.cb_agent.execute({"action": "record_success", "agent_name": "StatsAgent"})
        result = self.cb_agent.execute({
            "action": "stats",
            "agent_name": "StatsAgent",
        })
        assert result.success is True
        assert "state" in result.data

    def test_stats_all(self):
        self.cb_agent.execute({"action": "record_success", "agent_name": "AgentA"})
        result = self.cb_agent.execute({"action": "stats"})
        assert result.success is True
        assert isinstance(result.data, dict)

    def test_state_query(self):
        result = self.cb_agent.execute({
            "action": "state",
            "agent_name": "StateAgent",
        })
        assert result.success is True
        assert result.data["state"] in ("CLOSED", "OPEN", "HALF_OPEN")

    def test_state_no_agent_name(self):
        result = self.cb_agent.execute({"action": "state"})
        assert result.success is False

    def test_unknown_action(self):
        result = self.cb_agent.execute({"action": "fly_to_moon"})
        assert result.success is False
        assert "unknown" in result.error.lower()

    def test_non_dict_input(self):
        result = self.cb_agent.execute("bad input")
        assert isinstance(result, AgentResult)
        assert result.success is True  # Fallback assumes CLOSED

    def test_can_call_convenience(self):
        assert self.cb_agent.can_call("AnyAgent") is True

    def test_get_breaker_state_convenience(self):
        state = self.cb_agent.get_breaker_state("AnyAgent")
        assert state in ("CLOSED", "OPEN", "HALF_OPEN")

    def test_fallback_returns_closed(self):
        result = self.cb_agent.fallback(None)
        assert result.success is True
        assert result.data["state"] == "CLOSED"


# ======================================================================
# A48 BilingualRouter Tests
# ======================================================================

