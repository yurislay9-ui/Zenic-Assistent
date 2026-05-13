"""
Tests for ContextAgent BaseAgent interface, DAG integration, and edge cases.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.context_agent import (
    ContextAgent,
    ContextOutput,
    ContextEntry,
    TOTAL_CONTEXT_BUDGET,
)
from src.core.agents.schemas import IntentOutput


# ============================================================
#  TEST: BaseAgent interface
# ============================================================

class TestBaseAgentInterface:

    def test_build_prompt(self, context_agent):
        input_data = {
            "raw_context": "Previous: CREATE/FEATURE_ADD → FastAPI code",
            "intent_operation": "CREATE",
            "intent_goal": "FEATURE_ADD",
            "max_tokens": 200,
        }
        system, user = context_agent.build_prompt(input_data)
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "CREATE" in system or "FEATURE_ADD" in system

    def test_parse_response(self, context_agent):
        raw_response = "CREATE/FEATURE_ADD: FastAPI REST API | DEBUG/BUG_FIX: SQL whitelist"
        input_data = {"raw_context": "long context...", "max_tokens": 200}
        result = context_agent.parse_response(raw_response, input_data)
        assert isinstance(result, ContextOutput)
        assert result.source == "llm"

    def test_parse_response_empty(self, context_agent):
        result = context_agent.parse_response("", {})
        assert result is None

    def test_fallback(self, context_agent, sample_intent_output):
        input_data = {
            "message": "build API",
            "intent_output": sample_intent_output,
            "max_tokens": 200,
        }
        result = context_agent.fallback(input_data)
        assert isinstance(result, ContextOutput)
        assert result.source == "fallback"
        assert result.duration_ms >= 0


# ============================================================
#  TEST: Integración con DAG pipeline
# ============================================================

class TestDAGIntegration:

    def test_context_output_has_all_fields(self, context_agent, sample_intent_output):
        result = context_agent.prepare_context("test", sample_intent_output)
        assert hasattr(result, "compressed_context")
        assert hasattr(result, "relevant_memories")
        assert hasattr(result, "token_budget")
        assert hasattr(result, "context_scores")
        assert hasattr(result, "entries_used")
        assert hasattr(result, "entries_total")
        assert hasattr(result, "compression_ratio")
        assert hasattr(result, "source")
        assert hasattr(result, "duration_ms")

    def test_different_intents_produce_different_budgets(self, context_agent):
        create_budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        debug_budget = context_agent._allocate_budget("DEBUG", "BUG_FIX")
        assert create_budget["code"] != debug_budget["code"] or \
               create_budget["reasoning"] != debug_budget["reasoning"]

    def test_context_caching(self, context_agent, sample_intent_output):
        """Verifica que el cache compartido funciona."""
        result1 = context_agent.prepare_context("build API", sample_intent_output)
        cache_key = f"{sample_intent_output.operation}:{sample_intent_output.goal}"
        assert cache_key in context_agent._shared_context_cache

    def test_budget_stats(self, context_agent):
        stats = context_agent.budget_stats
        assert "default_budget" in stats
        assert "total_budget" in stats
        assert stats["total_budget"] == TOTAL_CONTEXT_BUDGET


# ============================================================
#  TEST: Edge cases
# ============================================================

class TestEdgeCases:

    def test_very_short_message(self, context_agent):
        result = context_agent.prepare_context("x", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)

    def test_very_long_message(self, context_agent):
        long_msg = "build " * 1000
        result = context_agent.prepare_context(long_msg, IntentOutput(operation="CREATE"))
        assert isinstance(result, ContextOutput)

    def test_no_semantic_engine(self):
        agent = ContextAgent(smart_memory=MagicMock())
        agent._smart_memory._working_memory = []
        result = agent.prepare_context("test", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)

    def test_no_smart_memory(self):
        agent = ContextAgent(semantic_engine=MagicMock())
        result = agent.prepare_context("test", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)

    def test_empty_working_memory(self, context_agent, mock_smart_memory):
        mock_smart_memory._working_memory = []
        result = context_agent.prepare_context("test", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)
        assert result.entries_total >= 0
