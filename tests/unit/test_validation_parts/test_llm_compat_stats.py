"""
Tests for ValidationAgent LLM path, legacy compatibility, wire and stats.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.schemas import ValidationInput, ValidationOutput, ValidationIssue
from src.core.agents.base import AgentResult


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestValidationLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_with_validation_input(self, agent):
        """Should build system + user prompt from ValidationInput."""
        system, user = agent.build_prompt(ValidationInput(
            target="code",
            content="eval(x)",
            rules=["security"],
            language="python",
        ))
        assert "validation" in system.lower()
        assert "code" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("some code to validate")
        assert "validation" in system.lower()

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"is_valid":false,"issues":[{"severity":"error","code":"dangerous_eval","message":"Use of eval()","line":1,"suggestion":"Use ast.literal_eval()"}],"suggestions":["Replace eval()"],"risk_score":0.3}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.is_valid is False
        assert len(result.issues) == 1
        assert result.issues[0].code == "dangerous_eval"
        assert result.risk_score == 0.3
        assert result.source == "llm"

    def test_parse_response_free_text(self, agent):
        """Should parse free text with bullet points."""
        raw = "Found issues:\n- Use of eval() is dangerous\n- Missing error handling"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert len(result.issues) >= 1
        assert result.source == "llm"

    def test_parse_response_empty(self, agent):
        """Should return None for very short/empty text."""
        result = agent.parse_response("short", None)
        assert result is None

    def test_parse_response_risk_score_clamped(self, agent):
        """Should clamp risk_score to 0-1 range."""
        raw = '{"is_valid":true,"issues":[],"suggestions":[],"risk_score":2.5}'
        result = agent.parse_response(raw, None)
        assert result.risk_score <= 1.0


# ============================================================
#  Test: Legacy Compatibility
# ============================================================

class TestValidationLegacyCompat:
    """Tests for to_validation_result() ChainValidator compatibility."""

    def test_to_validation_result(self, agent):
        """Should convert ValidationOutput to ValidationResult."""
        output = ValidationOutput(
            is_valid=False,
            issues=[
                ValidationIssue(severity="error", code="eval", message="Bad eval"),
                ValidationIssue(severity="warning", code="print", message="Print found"),
            ],
            risk_score=0.4,
        )
        with patch("src.core.chain_validator.ValidationResult") as MockResult:
            mock_result_instance = MagicMock()
            MockResult.return_value = mock_result_instance
            with patch("src.core.chain_validator.ValidationError", MagicMock):
                result = agent.to_validation_result(output)
                mock_result_instance.add_error.assert_called_once()
                mock_result_instance.add_warning.assert_called_once()


# ============================================================
#  Test: Wire and Stats
# ============================================================

class TestValidationWireAndStats:
    """Tests for wire() and stats tracking."""

    def test_wire_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        assert agent._semantic_engine is mock_se

    def test_wire_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_mem = MagicMock()
        agent.wire(smart_memory=mock_mem)
        assert agent._smart_memory is mock_mem

    def test_stats_after_fallback(self, agent):
        """Should track fallback calls in stats."""
        agent.fallback(ValidationInput(
            target="code", content="x = 1", language="python"
        ))
        stats = agent.stats
        assert stats["name"] == "validation"
        assert stats["total_calls"] >= 1

    def test_validate_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = ValidationOutput(
            is_valid=True, issues=[], risk_score=0.0, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.validate_with_runner(
            mock_runner, "code", "x = 1"
        )
        assert result.is_valid is True
        assert result.source == "llm"

    def test_validate_with_runner_failure_falls_back(self, agent):
        """Should fall back when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        result = agent.validate_with_runner(
            mock_runner, "code", "x = 1"
        )
        assert result.source == "fallback"
