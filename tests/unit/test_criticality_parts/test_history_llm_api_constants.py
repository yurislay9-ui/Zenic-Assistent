"""
Tests for CriticalityAgent history signal, confidence, LLM path,
high-level API, constants, wire and history recording.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.criticality_agent import (
    CriticalityAgent,
    LEVEL_FAST,
    LEVEL_MODERATE,
    LEVEL_SURGICAL,
    STR_TO_LEVEL,
    LEVEL_TO_PATH,
    GOAL_CRITICALITY_MAP,
    OP_CRITICALITY_MAP,
    CRITICALITY_ADJUSTMENTS,
)
from src.core.agents.schemas import (
    CriticalityInput,
    CriticalityOutput,
    IntentOutput,
)
from src.core.agents.base import AgentResult


# ============================================================
#  Test: History Signal
# ============================================================

class TestCriticalityHistorySignal:
    """Tests for historical pattern signal."""

    def test_history_elevates_for_matching_target(self, agent_with_history):
        """Should elevate criticality based on history of same target."""
        level = agent_with_history._history_signal("DELETE", "auth.py")
        assert level >= LEVEL_MODERATE

    def test_history_fast_for_new_target(self, agent_with_history):
        """Should return FAST for targets not in history."""
        level = agent_with_history._history_signal("SEARCH", "brand_new.py")
        assert level == LEVEL_FAST

    def test_no_history_returns_fast(self, agent):
        """Should return FAST when no history exists."""
        level = agent._history_signal("CREATE", "test.py")
        assert level == LEVEL_FAST


# ============================================================
#  Test: Confidence Computation
# ============================================================

class TestCriticalityConfidence:
    """Tests for confidence computation."""

    def test_all_signals_agree_high_confidence(self, agent):
        """Should have high confidence when all signals agree."""
        signals = [(3, 0.3), (3, 0.25), (3, 0.2), (3, 0.15), (3, 0.1)]
        confidence = agent._compute_confidence(signals, 3)
        assert confidence >= 0.9

    def test_signals_disagree_lower_confidence(self, agent):
        """Should have lower confidence when signals disagree."""
        signals = [(1, 0.3), (3, 0.25), (2, 0.2), (1, 0.15), (3, 0.1)]
        confidence = agent._compute_confidence(signals, 2)
        assert confidence < 0.9


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestCriticalityLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_with_criticality_input(self, agent):
        """Should build prompt from CriticalityInput."""
        system, user = agent.build_prompt(CriticalityInput(
            operation="DELETE",
            goal="SECURITY_HARDEN",
            target="auth.py",
        ))
        assert "criticality" in system.lower()
        assert "DELETE" in user

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"level":3,"reason":"Auth target detected","confidence":0.9}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.level == 3
        assert result.path == "high_crit"
        assert result.confidence == 0.9
        assert result.source == "llm"

    def test_parse_response_string_level(self, agent):
        """Should normalize string level in JSON response."""
        raw = '{"level":"critical","reason":"Security","confidence":0.8}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.level == 3

    def test_parse_response_just_number(self, agent):
        """Should parse a bare number response from LLM."""
        raw = "The criticality level is 2 for this operation"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.level == 2

    def test_parse_response_empty(self, agent):
        """Should return None for unparseable response."""
        raw = "xyzzy foo bar baz quux"
        result = agent.parse_response(raw, None)
        assert result is None

    def test_parse_response_level_clamped(self, agent):
        """Should clamp level to 1-3 range."""
        raw = '{"level":5,"reason":"test","confidence":0.5}'
        result = agent.parse_response(raw, None)
        assert result.level == 3


# ============================================================
#  Test: High-Level API
# ============================================================

class TestCriticalityHighLevelAPI:
    """Tests for assess_deterministic and assess_with_runner."""

    def test_assess_deterministic(self, agent):
        """Should assess criticality directly without LLM."""
        result = agent.assess_deterministic(
            operation="DELETE",
            goal="SECURITY_HARDEN",
            target="auth.py",
        )
        assert result.level >= LEVEL_MODERATE
        assert result.source == "fallback"

    def test_assess_deterministic_with_existing(self, agent):
        """Should not lower criticality below existing level."""
        result = agent.assess_deterministic(
            operation="SEARCH",
            goal="READABILITY",
            target="utils.py",
            existing_criticality=3,
        )
        assert result.level >= 3

    def test_assess_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = CriticalityOutput(
            level=3, path="high_crit", reason="Auth detected",
            confidence=0.9, source="llm",
            adjustments=CRITICALITY_ADJUSTMENTS[3],
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        intent_output = IntentOutput(
            operation="DELETE", goal="SECURITY_HARDEN", target="auth.py"
        )
        result = agent.assess_with_runner(mock_runner, intent_output)
        assert result.level == 3
        assert result.source == "llm"

    def test_assess_with_runner_failure_falls_back(self, agent):
        """Should fall back when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        intent_output = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD", target="utils.py"
        )
        result = agent.assess_with_runner(mock_runner, intent_output)
        assert result.source == "fallback"

    def test_assess_with_runner_elevation(self, agent):
        """Should not let LLM lower criticality below MacroRouter signal."""
        mock_runner = MagicMock()
        llm_output = CriticalityOutput(
            level=1, path="low_crit", reason="Looks safe",
            confidence=0.6, source="llm",
            adjustments=CRITICALITY_ADJUSTMENTS[1],
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        intent_output = IntentOutput(
            operation="DELETE", goal="SECURITY_HARDEN", target="auth.py"
        )
        result = agent.assess_with_runner(
            mock_runner, intent_output, existing_criticality=3
        )
        assert result.level >= 3


# ============================================================
#  Test: Constants and Adjustments
# ============================================================

class TestCriticalityConstants:
    """Tests for constants integrity."""

    def test_str_to_level_coverage(self):
        """STR_TO_LEVEL should map all expected strings."""
        assert STR_TO_LEVEL["standard"] == 1
        assert STR_TO_LEVEL["moderate"] == 2
        assert STR_TO_LEVEL["critical"] == 3

    def test_level_to_path_coverage(self):
        """LEVEL_TO_PATH should map all levels."""
        assert LEVEL_TO_PATH[1] == "low_crit"
        assert LEVEL_TO_PATH[2] == "standard"
        assert LEVEL_TO_PATH[3] == "high_crit"

    def test_criticality_adjustments_all_levels(self):
        """CRITICALITY_ADJUSTMENTS should have entries for levels 1, 2, 3."""
        assert 1 in CRITICALITY_ADJUSTMENTS
        assert 2 in CRITICALITY_ADJUSTMENTS
        assert 3 in CRITICALITY_ADJUSTMENTS

    def test_adjustments_code_agent_keys(self):
        """Each level should have code_agent adjustments."""
        for level in [1, 2, 3]:
            assert "code_agent" in CRITICALITY_ADJUSTMENTS[level]

    def test_adjustments_business_agent_keys(self):
        """Each level should have business_agent adjustments."""
        for level in [1, 2, 3]:
            assert "business_agent" in CRITICALITY_ADJUSTMENTS[level]

    def test_goal_criticality_map_security(self):
        """SECURITY_HARDEN should map to level 3."""
        assert GOAL_CRITICALITY_MAP["SECURITY_HARDEN"] == 3

    def test_op_criticality_map_delete(self):
        """DELETE should map to level 3."""
        assert OP_CRITICALITY_MAP["DELETE"] == 3


# ============================================================
#  Test: Wire and History Recording
# ============================================================

class TestCriticalityWireAndHistory:
    """Tests for wire() and history recording."""

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

    def test_wire_macro_router(self, agent):
        """Should update macro router reference via wire()."""
        mock_router = MagicMock()
        agent.wire(macro_router=mock_router)
        assert agent._macro_router is mock_router

    def test_history_recording(self, agent):
        """Should record history after fallback evaluation."""
        agent.fallback(CriticalityInput(
            operation="DELETE", goal="SECURITY_HARDEN", target="auth.py"
        ))
        assert len(agent._history) == 1
        assert agent._history[0]["op"] == "DELETE"

    def test_history_max_size(self, agent):
        """Should not exceed _history_max entries."""
        agent._history_max = 3
        for i in range(5):
            agent.fallback(CriticalityInput(
                operation="CREATE", goal="FEATURE_ADD", target=f"file_{i}.py"
            ))
        assert len(agent._history) <= 3
