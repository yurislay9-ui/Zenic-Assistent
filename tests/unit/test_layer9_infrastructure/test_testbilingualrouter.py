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



class TestBilingualRouter:
    """A48: Detect language and route to EN/ES handlers."""

    def setup_method(self):
        self.router = BilingualRouter()

    def test_detect_english(self):
        result = self.router.execute("Create a new feature for the application")
        assert isinstance(result, LanguageResult)
        assert result.lang == "en"
        assert result.source == "deterministic"

    def test_detect_spanish(self):
        result = self.router.execute("Crear una nueva funcionalidad para la aplicación")
        assert isinstance(result, LanguageResult)
        assert result.lang == "es"

    def test_detect_spanish_common_words(self):
        result = self.router.execute("Necesito crear un proyecto de base de datos")
        assert result.lang == "es"

    def test_detect_english_short(self):
        result = self.router.execute("Fix the bug")
        assert result.lang == "en"

    def test_empty_input_fallback(self):
        result = self.router.execute("")
        assert isinstance(result, LanguageResult)
        assert result.source == "fallback"
        assert result.lang == "en"

    def test_none_input_fallback(self):
        result = self.router.execute(None)
        assert isinstance(result, LanguageResult)
        assert result.lang == "en"

    def test_numeric_input(self):
        result = self.router.execute(12345)
        assert isinstance(result, LanguageResult)

    def test_confidence_range(self):
        result = self.router.execute("Create a new module")
        assert 0.0 <= result.confidence <= 1.0

    def test_text_preserved(self):
        text = "Hello world this is a test"
        result = self.router.execute(text)
        assert result.text == text

    def test_fallback_returns_english(self):
        result = self.router.fallback(None)
        assert result.lang == "en"
        assert result.confidence == 0.5
        assert result.source == "fallback"


# ======================================================================
# Integration: Full Infrastructure Pipeline Test
# ======================================================================

