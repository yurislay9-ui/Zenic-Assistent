"""
Tests for ReasoningAgent fallback, LLM path, conversion, and edge cases.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.schemas import ReasoningInput, ReasoningOutput
from src.core.agents.base import AgentResult


# ============================================================
#  ReasoningAgent: Fallback Reasoning
# ============================================================

class TestReasoningAgentFallback:
    """Tests for deterministic fallback reasoning."""

    def test_api_problem_type(self, reasoning_agent):
        """Should detect API problems and provide template response."""
        result = reasoning_agent.fallback(ReasoningInput(query="How to create a REST API?"))
        assert result.source == "fallback"
        assert "API" in result.answer or "api" in result.answer.lower()

    def test_auth_problem_type(self, reasoning_agent):
        """Should detect auth problems."""
        result = reasoning_agent.fallback(ReasoningInput(query="Implement login auth"))
        assert result.source == "fallback"
        assert "auth" in result.answer.lower() or "JWT" in result.answer

    def test_invoice_problem_type(self, reasoning_agent):
        """Should detect invoice problems."""
        result = reasoning_agent.fallback(ReasoningInput(query="Build invoice system"))
        assert result.source == "fallback"
        assert "invoice" in result.answer.lower() or "factura" in result.answer.lower()

    def test_crm_problem_type(self, reasoning_agent):
        """Should detect CRM problems."""
        result = reasoning_agent.fallback(ReasoningInput(query="CRM for customers"))
        assert result.source == "fallback"
        assert "crm" in result.answer.lower() or "CRM" in result.answer

    def test_unknown_problem_type(self, reasoning_agent):
        """Should handle unknown problem types with generic response."""
        result = reasoning_agent.fallback(ReasoningInput(query="Random question about life"))
        assert result.source == "fallback"
        assert result.answer

    def test_fallback_steps_structure(self, reasoning_agent):
        """Should produce structured reasoning steps."""
        result = reasoning_agent.fallback(ReasoningInput(query="Build auth system", max_steps=3))
        assert len(result.steps) >= 1
        assert result.steps[0].step_number == 1
        assert result.steps[0].description
        assert result.steps[0].conclusion

    def test_fallback_confidence_is_low(self, reasoning_agent):
        """Fallback confidence should be in the 0-0.5 range."""
        result = reasoning_agent.fallback(ReasoningInput(query="Build something"))
        assert 0.0 <= result.confidence <= 0.5

    def test_mode_preserved(self, reasoning_agent):
        """Should preserve the requested reasoning mode."""
        result = reasoning_agent.fallback(ReasoningInput(query="test", mode="self_reflect"))
        assert result.mode == "self_reflect"

    def test_spanish_query(self, reasoning_agent):
        """Should handle Spanish queries."""
        result = reasoning_agent.fallback(ReasoningInput(query="crear sistema de autenticación"))
        assert result.source == "fallback"
        assert result.answer


class TestReasoningAgentLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_step_by_step(self, reasoning_agent):
        """Should build step_by_step prompt."""
        system, user = reasoning_agent.build_prompt(
            ReasoningInput(query="How to build an API?", mode="step_by_step")
        )
        assert "step-by-step" in system.lower() or "step by step" in system.lower()
        assert "build an API" in user

    def test_build_prompt_self_reflect(self, reasoning_agent):
        """Should build self_reflect prompt."""
        system, user = reasoning_agent.build_prompt(
            ReasoningInput(query="Is this correct?", mode="self_reflect")
        )
        assert "self-reflect" in system.lower() or "critique" in system.lower()

    def test_build_prompt_with_context(self, reasoning_agent):
        """Should build with_context prompt."""
        system, user = reasoning_agent.build_prompt(
            ReasoningInput(query="Build auth", mode="with_context", context="Using FastAPI")
        )
        assert "context" in system.lower() or "context" in user.lower()

    def test_parse_json_response(self, reasoning_agent):
        """Should parse valid JSON reasoning response."""
        raw = '{"answer":"Use JWT tokens","confidence":0.8,"steps":[{"step_number":1,"description":"Setup auth","conclusion":"Use JWT"}],"refinements":0}'
        result = reasoning_agent.parse_response(raw, None)
        assert result is not None
        assert result.answer == "Use JWT tokens"
        assert result.confidence == 0.8
        assert len(result.steps) == 1
        assert result.source == "llm"

    def test_parse_free_text_response(self, reasoning_agent):
        """Should parse free text when no JSON found."""
        raw = "The best approach is to use JWT tokens for authentication. Therefore, implement JWT middleware."
        result = reasoning_agent.parse_response(raw, None)
        assert result is not None
        assert result.source == "llm"

    def test_parse_empty_response(self, reasoning_agent):
        """Should handle empty responses."""
        result = reasoning_agent.parse_response("", None)
        assert result is None

    def test_reason_with_runner_llm_success(self, reasoning_agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = ReasoningOutput(
            answer="Use FastAPI", confidence=0.8, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = reasoning_agent.reason_with_runner(mock_runner, "Build API")
        assert result.answer == "Use FastAPI"
        assert result.source == "llm"

    def test_reason_with_runner_fallback(self, reasoning_agent):
        """Should use fallback when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error"
        )
        result = reasoning_agent.reason_with_runner(mock_runner, "Build auth")
        assert result.source == "fallback"


class TestReasoningAgentConversion:
    """Tests for ReasoningOutput → ReasoningResult conversion."""

    def test_to_reasoning_result(self, reasoning_agent):
        """Should convert to ReasoningResult correctly."""
        from src.core.reasoning_engine import ReasoningMode, ReasoningResult

        output = ReasoningOutput(
            answer="Use JWT",
            confidence=0.7,
            mode="step_by_step",
            steps=[],
            source="llm",
        )
        result = reasoning_agent.to_reasoning_result(output)
        assert isinstance(result, ReasoningResult)
        assert result.answer == "Use JWT"
        assert result.mode == ReasoningMode.STEP_BY_STEP
        assert result.source == "llm"

    def test_to_reasoning_result_self_reflect(self, reasoning_agent):
        """Should map self_reflect mode correctly."""
        from src.core.reasoning_engine import ReasoningMode

        output = ReasoningOutput(mode="self_reflect")
        result = reasoning_agent.to_reasoning_result(output)
        assert result.mode == ReasoningMode.SELF_REFLECT


class TestReasoningAgentEdgeCases:
    """Edge case tests for ReasoningAgent."""

    def test_empty_query(self, reasoning_agent):
        """Should handle empty queries."""
        result = reasoning_agent.fallback(ReasoningInput(query=""))
        assert result is not None
        assert result.source == "fallback"

    def test_very_long_query(self, reasoning_agent):
        """Should handle very long queries."""
        long_query = "How to build " + "an API " * 200
        result = reasoning_agent.fallback(ReasoningInput(query=long_query))
        assert result is not None

    def test_stats_tracking(self, reasoning_agent):
        """Should track stats after fallback."""
        reasoning_agent.fallback(ReasoningInput(query="test"))
        stats = reasoning_agent.stats
        assert stats["name"] == "reasoning"
        assert stats["total_calls"] >= 1

    def test_wire_semantic_engine(self, reasoning_agent):
        """Should accept semantic engine via wire()."""
        mock_sem = MagicMock()
        mock_sem.is_loaded = True
        reasoning_agent.wire(semantic_engine=mock_sem)
        assert reasoning_agent._semantic_engine is mock_sem
