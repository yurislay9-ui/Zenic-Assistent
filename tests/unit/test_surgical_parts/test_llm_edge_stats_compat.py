"""
Tests for SurgicalAgent LLM path, edge cases, stats, and backward compatibility.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.surgical_agent import SurgicalAgent, VALID_OPERATIONS, VALID_GOALS
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Test: LLM Path
# ============================================================

class TestSurgicalAgentLLMPath:
    """Tests for the LLM prompt building and response parsing."""

    def test_build_prompt_compact(self, agent):
        """SurgicalAgent should use compact prompts for 600-token limit."""
        system, user = agent.build_prompt(IntentInput(
            message="crear modulo auth.py", context=""
        ))
        assert "Classify" in system
        assert "JSON" in system
        assert "crear modulo auth.py" in user

    def test_parse_response_valid_json(self, agent):
        raw = '{"operation":"CREATE","goal":"FEATURE_ADD","target":"auth.py","language":"python","entities":{},"template_type":"api","criticality":"standard","confidence":0.9}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "CREATE"
        assert result.confidence == 0.9

    def test_parse_response_markdown_json(self, agent):
        raw = '```json\n{"operation":"DEBUG","goal":"BUG_FIX","confidence":0.75}\n```'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "DEBUG"

    def test_classify_with_runner_fuses_llm_with_tfidf(self, agent):
        """classify_with_runner should fuse LLM result with TF-IDF."""
        mock_runner = MagicMock()
        llm_output = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            target="auth.py", confidence=0.9, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.classify_with_runner(mock_runner, "crear modulo auth.py")
        assert result.operation == "CREATE"
        assert result.confidence > 0

    def test_classify_with_runner_failure_uses_fallback(self, agent):
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error", error="LLM timeout"
        )
        result = agent.classify_with_runner(mock_runner, "crear modulo auth.py")
        assert result.operation == "CREATE"


# ============================================================
#  Test: Edge Cases
# ============================================================

class TestSurgicalAgentEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_message(self, agent):
        result = agent.fallback(IntentInput(message=""))
        assert result is not None
        assert result.operation in VALID_OPERATIONS

    def test_very_long_message(self, agent):
        long_msg = "crear " + "modulo " * 500
        result = agent.fallback(IntentInput(message=long_msg))
        assert result is not None

    def test_special_characters(self, agent):
        result = agent.fallback(IntentInput(message="crear módulo auth.py con ñ y áéíóú"))
        assert result is not None

    def test_confidence_always_in_range(self, agent):
        for msg in ["crear", "debug error", "fix bug", "hello world", ""]:
            result = agent.fallback(IntentInput(message=msg))
            assert 0.0 <= result.confidence <= 1.0

    def test_fallback_confidence_is_low(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.confidence <= 0.5

    def test_smart_memory_failure_graceful(self, agent):
        mock_memory = MagicMock()
        mock_memory.check_cache.side_effect = Exception("DB error")
        agent.wire(smart_memory=mock_memory)
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation in VALID_OPERATIONS


# ============================================================
#  Test: Stats & Wiring
# ============================================================

class TestSurgicalAgentStats:
    """Tests for agent statistics and wiring."""

    def test_initial_stats(self, agent):
        stats = agent.stats
        assert stats["name"] == "surgical"
        assert stats["total_calls"] == 0

    def test_stats_after_fallback(self, agent):
        agent.fallback(IntentInput(message="crear modulo"))
        stats = agent.stats
        assert stats["total_calls"] >= 1

    def test_wire_updates_semantic_engine(self, agent):
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        agent.wire(semantic_engine=mock_semantic)
        assert agent._semantic_engine is mock_semantic

    def test_wire_updates_smart_memory(self, agent):
        mock_memory = MagicMock()
        agent.wire(smart_memory=mock_memory)
        assert agent._smart_memory is mock_memory


# ============================================================
#  Test: Backward Compatibility with IntentAgent
# ============================================================

class TestSurgicalAgentBackwardCompat:
    """Tests that SurgicalAgent is a drop-in replacement for IntentAgent."""

    def test_has_classify_method(self, agent):
        """SurgicalAgent must have classify() method."""
        assert hasattr(agent, 'classify')
        assert callable(agent.classify)

    def test_has_classify_with_runner_method(self, agent):
        """SurgicalAgent must have classify_with_runner() method."""
        assert hasattr(agent, 'classify_with_runner')
        assert callable(agent.classify_with_runner)

    def test_has_to_intent_payload_method(self, agent):
        """SurgicalAgent must have to_intent_payload() method."""
        assert hasattr(agent, 'to_intent_payload')
        assert callable(agent.to_intent_payload)

    def test_has_extract_code_block_static(self):
        """SurgicalAgent must have _extract_code_block() static method."""
        assert hasattr(SurgicalAgent, '_extract_code_block')
        code = "def hello():\n    pass"
        lang, extracted = SurgicalAgent._extract_code_block(
            f"```python\n{code}\n```"
        )
        assert lang == "python"
        assert extracted is not None

    def test_intent_output_compatible(self, agent):
        """SurgicalAgent output must be compatible with IntentOutput schema."""
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert isinstance(result, IntentOutput)
        assert result.operation in VALID_OPERATIONS
        assert result.goal in VALID_GOALS
