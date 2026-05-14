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



class TestAuditLoggerAgent:
    """A46: Log all agent decisions for post-mortem analysis."""

    def setup_method(self):
        self.auditor = AuditLoggerAgent()

    def test_record_entry(self):
        result = self.auditor.execute({
            "action": "record",
            "agent": "TestAgent",
            "source": "deterministic",
            "duration_ms": 10.5,
            "retry_count": 0,
        })
        assert isinstance(result, AgentResult)
        assert result.success is True

    def test_record_entry_with_dict(self):
        result = self.auditor.execute({
            "action": "record",
            "entry": {
                "agent": "TestAgent2",
                "source": "fallback",
                "duration_ms": 5.0,
            },
        })
        assert result.success is True

    def test_record_audit_entry_object(self):
        entry = AuditEntry(
            agent="DirectEntry",
            source="deterministic",
            duration_ms=3.0,
        )
        result = self.auditor.execute({
            "action": "record",
            "entry": entry,
        })
        assert result.success is True

    def test_query_entries(self):
        # Record some entries first
        for i in range(5):
            self.auditor.execute({
                "action": "record",
                "agent": f"QueryAgent_{i}",
                "source": "deterministic",
                "duration_ms": float(i),
            })

        result = self.auditor.execute({
            "action": "query",
            "count": 3,
        })
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) <= 3

    def test_query_by_agent(self):
        self.auditor.record_decision(
            agent_name="SpecificAgent",
            source="deterministic",
            duration_ms=10.0,
        )

        result = self.auditor.execute({
            "action": "query",
            "agent_name": "SpecificAgent",
            "count": 10,
        })
        assert result.success is True
        assert isinstance(result.data, list)

    def test_analyze_failure_pattern(self):
        # Record some failures
        for _ in range(5):
            self.auditor.record_decision(
                agent_name="FailingAgent",
                source="fallback",
                duration_ms=100.0,
            )

        result = self.auditor.execute({
            "action": "analyze",
            "agent_name": "FailingAgent",
        })
        assert result.success is True
        assert "risk_level" in result.data
        assert "failure_rate" in result.data

    def test_stats(self):
        self.auditor.record_decision(
            agent_name="StatsAgent",
            source="deterministic",
            duration_ms=5.0,
        )

        result = self.auditor.execute({"action": "stats"})
        assert result.success is True
        assert "agents_tracked" in result.data
        assert "total_entries" in result.data

    def test_unknown_action(self):
        result = self.auditor.execute({"action": "invalid_action"})
        assert result.success is False
        assert "unknown" in result.error.lower()

    def test_non_dict_input(self):
        result = self.auditor.execute("not a dict")
        assert isinstance(result, AgentResult)
        assert result.success is True  # Fallback is non-fatal

    def test_record_decision_convenience(self):
        self.auditor.record_decision(
            agent_name="ConvenienceAgent",
            source="deterministic",
            duration_ms=7.5,
            retry_count=0,
            circuit_breaker_state="CLOSED",
        )
        # Verify it was recorded
        recent = self.auditor.get_recent("ConvenienceAgent", 1)
        assert len(recent) >= 1
        assert recent[0].agent == "ConvenienceAgent"

    def test_get_failure_pattern_convenience(self):
        pattern = self.auditor.get_failure_pattern()
        assert "risk_level" in pattern

    def test_fallback_non_fatal(self):
        result = self.auditor.fallback(None)
        assert result.success is True
        assert result.source == "fallback"


# ======================================================================
# A47 CircuitBreakerManagerAgent Tests
# ======================================================================

