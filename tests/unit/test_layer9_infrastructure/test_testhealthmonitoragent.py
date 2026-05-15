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

from src.core.agents.infrastructure import (
    AgentRunner,
    HealthMonitorAgent,
    AuditLoggerAgent,
    CircuitBreakerManagerAgent,
)
from src.core.agents.understanding import BilingualRouter
from src.core.agents.resilience import (
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
from src.core.agents.schemas import (
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



class TestHealthMonitorAgent:
    """A45: Track health of all agents and LLM."""

    def setup_method(self):
        self.monitor = HealthMonitorAgent()

    def test_system_snapshot(self):
        result = self.monitor.execute(None)
        assert isinstance(result, HealthSnapshot)
        assert result.healthy is True  # No data = healthy by default

    def test_system_snapshot_dict_input(self):
        result = self.monitor.execute({"action": "system"})
        assert isinstance(result, HealthSnapshot)

    def test_system_snapshot_all_string(self):
        result = self.monitor.execute("all")
        assert isinstance(result, HealthSnapshot)

    def test_agent_snapshot(self):
        # Record some data first
        self.monitor.record_call("TestAgent", success=True, latency_s=0.1)
        result = self.monitor.execute({"action": "agent", "agent_name": "TestAgent"})
        assert isinstance(result, HealthSnapshot)
        assert "TestAgent" in result.success_rates
        assert result.success_rates["TestAgent"] == 1.0

    def test_agent_snapshot_by_string(self):
        self.monitor.record_call("MyAgent", success=True, latency_s=0.05)
        result = self.monitor.execute("MyAgent")
        assert isinstance(result, HealthSnapshot)
        assert "MyAgent" in result.success_rates

    def test_unhealthy_snapshot(self):
        # Record failures
        for _ in range(10):
            self.monitor.record_call("SickAgent", success=False, latency_s=1.0)
        result = self.monitor.execute({"action": "unhealthy"})
        assert isinstance(result, HealthSnapshot)

    def test_record_call_and_check_health(self):
        self.monitor.record_call("GoodAgent", success=True, latency_s=0.01)
        assert self.monitor.is_healthy("GoodAgent") is True

    def test_is_healthy_unknown_agent(self):
        assert self.monitor.is_healthy("UnknownAgent") is True  # No data = healthy

    def test_fallback_returns_healthy(self):
        result = self.monitor.fallback(None)
        assert isinstance(result, HealthSnapshot)
        assert result.healthy is True

    def test_snapshot_has_timestamp(self):
        result = self.monitor.execute("all")
        assert result.timestamp > 0


# ======================================================================
# A46 AuditLoggerAgent Tests
# ======================================================================

