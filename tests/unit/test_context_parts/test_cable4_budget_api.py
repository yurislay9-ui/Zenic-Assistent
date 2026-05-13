"""
Tests for ContextAgent CABLE 4 (prefetch), token budget, and high-level API.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.context_agent import (
    ContextAgent,
    ContextOutput,
    ContextEntry,
    DEFAULT_TOKEN_BUDGET,
    TOTAL_CONTEXT_BUDGET,
)
from src.core.agents.schemas import IntentOutput


# ============================================================
#  TEST: CABLE 4 — Pre-fetch de memorias relevantes
# ============================================================

class TestCable4Prefetch:

    def test_prefetch_similar_solutions(self, context_agent, mock_smart_memory):
        results = context_agent._prefetch_relevant("build API", "CREATE", "FEATURE_ADD")
        assert len(results) >= 1
        assert results[0]["type"] == "similar_solution"

    def test_prefetch_debug_episodes(self, context_agent, mock_smart_memory):
        mock_smart_memory.find_episodes.return_value = [
            {"description": "SQL injection fixed", "outcome": "success"}
        ]
        results = context_agent._prefetch_relevant("fix bug", "DEBUG", "BUG_FIX")
        types = [r["type"] for r in results]
        assert "error_episode" in types

    def test_prefetch_create_patterns(self, context_agent, mock_smart_memory):
        results = context_agent._prefetch_relevant("build app", "CREATE", "FEATURE_ADD")
        types = [r["type"] for r in results]
        assert "procedural_pattern" in types

    def test_prefetch_no_memory(self):
        agent = ContextAgent()
        results = agent._prefetch_relevant("test", "SEARCH", "FEATURE_ADD")
        assert results == []


# ============================================================
#  TEST: Presupuesto de tokens
# ============================================================

class TestTokenBudget:

    def test_default_budget(self):
        total = sum(DEFAULT_TOKEN_BUDGET.values())
        assert total > 0
        assert all(v > 0 for v in DEFAULT_TOKEN_BUDGET.values())

    def test_create_budget_increases_code(self, context_agent):
        budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        assert budget["code"] >= DEFAULT_TOKEN_BUDGET["code"]

    def test_debug_budget_increases_reasoning(self, context_agent):
        budget = context_agent._allocate_budget("DEBUG", "BUG_FIX")
        assert budget["reasoning"] >= DEFAULT_TOKEN_BUDGET["reasoning"]

    def test_security_budget_increases_validation(self, context_agent):
        normal_budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        security_budget = context_agent._allocate_budget("CREATE", "SECURITY_HARDEN")
        security_val_ratio = security_budget["validation"] / sum(security_budget.values())
        normal_val_ratio = normal_budget["validation"] / sum(normal_budget.values())
        assert security_val_ratio >= normal_val_ratio

    def test_budget_does_not_exceed_total(self, context_agent):
        budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        total = sum(budget.values())
        assert total <= TOTAL_CONTEXT_BUDGET + 50

    def test_get_budget_for_agent(self, context_agent):
        assert context_agent.get_token_budget_for("code") == DEFAULT_TOKEN_BUDGET["code"]
        assert context_agent.get_token_budget_for("reasoning") == DEFAULT_TOKEN_BUDGET["reasoning"]
        assert context_agent.get_token_budget_for("unknown") == 100


# ============================================================
#  TEST: High-level API
# ============================================================

class TestHighLevelAPI:

    def test_prepare_context(self, context_agent, sample_intent_output):
        result = context_agent.prepare_context(
            message="build a REST API",
            intent_output=sample_intent_output,
        )
        assert isinstance(result, ContextOutput)
        assert result.source == "fallback"
        assert isinstance(result.compressed_context, str)
        assert isinstance(result.token_budget, dict)
        assert isinstance(result.relevant_memories, list)

    def test_prepare_context_no_intent(self, context_agent):
        result = context_agent.prepare_context("test message")
        assert isinstance(result, ContextOutput)
        assert result.entries_total >= 0

    def test_prepare_context_with_runner_no_llm(self, context_agent, sample_intent_output):
        runner = MagicMock()
        runner._mini_ai = None
        result = context_agent.prepare_context_with_runner(
            runner, "build API", sample_intent_output
        )
        assert isinstance(result, ContextOutput)

    def test_get_context_for_agent(self, context_agent, sample_intent_output):
        ctx = context_agent.get_context_for_agent("code", sample_intent_output)
        assert isinstance(ctx, str)

    def test_get_context_for_agent_dedup(self, context_agent, sample_intent_output):
        """Verifica deduplicación: segunda llamada retorna vacío."""
        ctx1 = context_agent.get_context_for_agent("code", sample_intent_output)
        ctx2 = context_agent.get_context_for_agent("code", sample_intent_output)
        assert ctx2 == ""

    def test_reset_agent_tracking(self, context_agent, sample_intent_output):
        context_agent.get_context_for_agent("code", sample_intent_output)
        context_agent.reset_agent_tracking()
        ctx = context_agent.get_context_for_agent("code", sample_intent_output)

    def test_get_compressed_working_context(self, context_agent, sample_intent_output):
        ctx = context_agent.get_compressed_working_context(sample_intent_output, 200)
        assert isinstance(ctx, str)
