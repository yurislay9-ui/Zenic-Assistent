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



class TestAgentRunner:
    """A44: Execute agents with full resilience."""

    def setup_method(self):
        self.runner = AgentRunner()
        self.echo = EchoAgent()
        self.runner.register(self.echo)

    def test_register_agent(self):
        assert "EchoAgent" in self.runner.registered_names

    def test_register_many(self):
        another = EchoAgent(name="AnotherAgent")
        self.runner.register_many([another])
        assert "AnotherAgent" in self.runner.registered_names

    def test_get_agent(self):
        agent = self.runner.get_agent("EchoAgent")
        assert agent is not None
        assert agent.name == "EchoAgent"

    def test_get_agent_not_found(self):
        agent = self.runner.get_agent("NonExistent")
        assert agent is None

    def test_execute_by_name(self):
        result = self.runner.execute({
            "agent_name": "EchoAgent",
            "input": "hello world",
        })
        assert isinstance(result, AgentResult)
        assert result.success is True

    def test_execute_by_instance(self):
        direct_echo = EchoAgent(name="DirectEcho")
        result = self.runner.execute({
            "agent": direct_echo,
            "input": "direct test",
        })
        assert isinstance(result, AgentResult)
        assert result.success is True

    def test_execute_nonexistent_agent(self):
        result = self.runner.execute({
            "agent_name": "GhostAgent",
            "input": "test",
        })
        assert isinstance(result, AgentResult)
        assert result.success is False

    def test_execute_invalid_input(self):
        result = self.runner.execute("not a dict")
        assert isinstance(result, AgentResult)
        assert result.success is False

    def test_run_agent_convenience(self):
        raw = self.runner.run_agent("EchoAgent", "convenience test")
        assert isinstance(raw, dict)
        assert raw.get("success") is True

    def test_run_agent_not_registered(self):
        raw = self.runner.run_agent("GhostAgent", "test")
        assert raw["success"] is False
        assert "not registered" in raw["error"].lower()

    def test_fallback_returns_failure(self):
        result = self.runner.fallback(None)
        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.source == "fallback"


# ======================================================================
# A45 HealthMonitorAgent Tests
# ======================================================================

