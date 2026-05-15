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



class TestInfrastructurePipeline:
    """End-to-end infrastructure pipeline through all Layer 9 agents."""

    def test_full_resilience_pipeline(self):
        """Agent execution → health check → audit → circuit breaker verification."""
        # 1. Set up shared infrastructure
        fast_retry = AgentRetryConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)
        cb_manager = CircuitBreakerManager()
        health_monitor = GlobalHealthMonitor()
        audit_logger = AuditLogger()

        # 2. Create agents with shared infrastructure
        echo = EchoAgent(
            name="PipelineEcho",
            circuit_breaker_manager=cb_manager,
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=fast_retry,
        )

        runner = AgentRunner(
            circuit_breaker_manager=cb_manager,
            bulkhead_manager=BulkheadManager(),
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=fast_retry,
        )
        runner.register(echo)

        # 3. Execute agent through runner
        result = runner.execute({
            "agent_name": "PipelineEcho",
            "input": "pipeline test",
        })
        assert result.success is True

        # 4. Check health
        health_agent = HealthMonitorAgent(health_monitor=health_monitor)
        health_snap = health_agent.execute("PipelineEcho")
        assert isinstance(health_snap, HealthSnapshot)

        # 5. Check audit trail
        audit_agent = AuditLoggerAgent(audit_logger=audit_logger)
        audit_result = audit_agent.execute({"action": "query", "count": 5})
        assert audit_result.success is True

        # 6. Check circuit breaker state
        cb_agent = CircuitBreakerManagerAgent(circuit_breaker_manager=cb_manager)
        cb_result = cb_agent.execute({
            "action": "check",
            "agent_name": "PipelineEcho",
        })
        assert cb_result.data["can_call"] is True

    def test_circuit_breaker_blocks_failing_agent(self):
        """Circuit breaker should block agent after consecutive failures."""
        fast_retry = AgentRetryConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)
        cb_manager = CircuitBreakerManager()
        health_monitor = GlobalHealthMonitor()
        audit_logger = AuditLogger()

        # Use a name that maps to "understanding" group (threshold=3)
        failing = FailingAgent(
            name="A01_IntentClassifier",
            circuit_breaker_manager=cb_manager,
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=fast_retry,
        )

        # Run the failing agent multiple times to trip the breaker
        for _ in range(5):
            failing.run("test input")

        # Check circuit breaker using the SAME manager
        cb_agent = CircuitBreakerManagerAgent(circuit_breaker_manager=cb_manager)
        cb_result = cb_agent.execute({
            "action": "check",
            "agent_name": "A01_IntentClassifier",
        })
        assert cb_result.data["can_call"] is False

    def test_bilingual_router_in_pipeline(self):
        """BilingualRouter should correctly route mixed-language inputs."""
        router = BilingualRouter()

        # English input
        en_result = router.execute("Create a payment module")
        assert en_result.lang == "en"

        # Spanish input
        es_result = router.execute("Crear un módulo de pago")
        assert es_result.lang == "es"
