"""
Tests for AgentCache and AgentRunner.
"""

import time
import pytest
from unittest.mock import MagicMock

from src.core.agents.base import AgentResult
from src.core.agents.runner import AgentRunner
from src.core.agents.cache import AgentCache
from src.core.agents.schemas import IntentInput, IntentOutput

from .conftest import SampleAgent, BrokenAgent


# ============================================================
#  AGENT CACHE TESTS
# ============================================================

class TestAgentCache:
    """Tests para AgentCache."""

    def test_cache_miss(self):
        cache = AgentCache()
        result = cache.get("test_agent", "hello")
        assert result is None

    def test_cache_put_and_get(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput(operation="CREATE"))
        result = cache.get("test_agent", "hello")
        assert result is not None
        assert result.operation == "CREATE"

    def test_cache_different_agents(self):
        cache = AgentCache()
        cache.put("agent_a", "hello", IntentOutput(operation="CREATE"))
        cache.put("agent_b", "hello", IntentOutput(operation="DELETE"))

        result_a = cache.get("agent_a", "hello")
        result_b = cache.get("agent_b", "hello")
        assert result_a.operation == "CREATE"
        assert result_b.operation == "DELETE"

    def test_cache_different_inputs(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput(operation="CREATE"))
        result = cache.get("test_agent", "goodbye")
        assert result is None

    def test_cache_stats(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput())
        cache.get("test_agent", "hello")   # hit
        cache.get("test_agent", "world")   # miss

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_clear(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput())
        cache.clear()
        result = cache.get("test_agent", "hello")
        assert result is None

    def test_cache_max_size_eviction(self):
        cache = AgentCache(max_size=3)
        cache.put("a", "1", IntentOutput(operation="A1"))
        cache.put("b", "2", IntentOutput(operation="B2"))
        cache.put("c", "3", IntentOutput(operation="C3"))
        # This should trigger eviction
        cache.put("d", "4", IntentOutput(operation="D4"))
        # Cache should have max 3 entries (one was evicted)
        assert len(cache._cache) <= 3

    def test_cache_ttl_expiration(self):
        cache = AgentCache(ttl_seconds=0)  # Expira inmediatamente
        cache.put("test_agent", "hello", IntentOutput())
        time.sleep(0.01)
        result = cache.get("test_agent", "hello")
        assert result is None  # Should be expired

    def test_cache_with_dataclass_input(self):
        cache = AgentCache()
        inp = IntentInput(message="Create login", context="web")
        cache.put("intent", inp, IntentOutput(operation="CREATE"))
        result = cache.get("intent", inp)
        assert result is not None

    def test_cache_with_dict_input(self):
        cache = AgentCache()
        inp = {"key": "value", "num": 42}
        cache.put("test", inp, IntentOutput())
        result = cache.get("test", inp)
        assert result is not None


# ============================================================
#  AGENT RUNNER TESTS
# ============================================================

class TestAgentRunner:
    """Tests para AgentRunner."""

    def _make_mock_ai(self, response='{"operation": "CREATE", "goal": "FEATURE_ADD", "confidence": 0.9}'):
        """Crea un MiniAIEngine mock."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = response
        return mock_ai

    def test_runner_with_fallback_no_ai(self):
        """Runner sin IA debe usar fallback."""
        runner = AgentRunner(mini_ai=None, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "Create a user")

        assert result.success is True
        assert result.source == "fallback"
        assert result.data.operation == "SEARCH"

    def test_runner_with_llm_success(self):
        """Runner con IA que responde correctamente."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "Create a login page")

        assert result.success is True
        assert result.source == "llm"
        assert result.data.operation == "CREATE"
        assert result.data.confidence == 0.9

    def test_runner_with_llm_failure_then_fallback(self):
        """Runner donde LLM falla, debe usar fallback."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = None  # LLM returns nothing

        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "test")

        assert result.success is True
        assert result.source == "fallback"

    def test_runner_with_invalid_response_then_fallback(self):
        """Runner donde LLM devuelve respuesta inválida."""
        mock_ai = self._make_mock_ai(response="not valid json at all")
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "test")

        assert result.source == "fallback"

    def test_runner_with_cache_hit(self):
        """Runner con cache habilitado debe hacer hit en segunda llamada."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=True)
        agent = SampleAgent()

        # Primera llamada: cache miss → LLM
        result1 = runner.run(agent, "Create a login")
        assert result1.source == "llm"
        assert result1.cache_hit is False

        # Segunda llamada: cache hit
        result2 = runner.run(agent, "Create a login")
        assert result2.source == "cache"
        assert result2.cache_hit is True

    def test_runner_with_cache_disabled(self):
        """Runner con cache deshabilitado no debe cachear."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()

        result1 = runner.run(agent, "Create a login")
        result2 = runner.run(agent, "Create a login")

        # Ambas llamadas van al LLM (no hay cache)
        assert result1.source == "llm"
        assert result2.source == "llm"

    def test_runner_stats(self):
        """Runner debe trackear estadísticas."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=True)
        agent = SampleAgent()

        runner.run(agent, "test1")
        runner.run(agent, "test1")  # cache hit
        runner.run(agent, "test2")  # cache miss

        stats = runner.stats
        assert stats["total_calls"] == 3
        assert stats["cache_hits"] == 1
        assert stats["llm_calls"] >= 2

    def test_runner_clear_cache(self):
        """Runner.clear_cache debe limpiar el cache."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=True)
        agent = SampleAgent()

        runner.run(agent, "test")
        runner.clear_cache()

        result = runner.run(agent, "test")
        assert result.source == "llm"  # No cache hit

    def test_runner_update_engines(self):
        """Runner.update_engines debe actualizar referencias."""
        runner = AgentRunner(mini_ai=None)
        assert runner._mini_ai is None

        mock_ai = self._make_mock_ai()
        runner.update_engines(mini_ai=mock_ai)
        assert runner._mini_ai is mock_ai

    def test_broken_agent_always_fallback(self):
        """Agente con parse_response que siempre falla."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = BrokenAgent()
        result = runner.run(agent, "test")

        assert result.source == "fallback"

    def test_runner_duration_tracked(self):
        """Runner debe trackear duración."""
        runner = AgentRunner(mini_ai=None, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "test")

        assert result.duration_ms >= 0

    def test_run_raw_without_ai(self):
        """run_raw sin IA debe retornar None."""
        runner = AgentRunner(mini_ai=None)
        result = runner.run_raw("system", "user")
        assert result is None

    def test_run_raw_with_ai(self):
        """run_raw con IA debe llamar al LLM."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai)
        result = runner.run_raw("system", "user")
        assert result is not None
        mock_ai._call_llm.assert_called_once()
