"""Tests for IntentAgent conversion, LLM path, SemanticEngine, SmartMemory, and runner integration."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.intent_agent import IntentAgent, VALID_OPERATIONS
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Test: IntentOutput → IntentPayload Conversion
# ============================================================

class TestIntentAgentConversion:
    """Tests for IntentOutput to IntentPayload conversion (pipeline compat)."""

    def test_to_intent_payload_basic(self, agent):
        """Should convert IntentOutput to IntentPayload correctly."""
        output = IntentOutput(
            operation="CREATE",
            goal="FEATURE_ADD",
            target="auth.py",
            language="python",
            confidence=0.8,
            source="llm",
        )
        payload = agent.to_intent_payload(output, context="crear modulo auth.py")

        assert payload.op == "CREATE"
        assert payload.goal == "FEATURE_ADD"
        assert payload.target == "auth.py"
        assert payload.confidence == 0.8
        assert payload.language == "python"
        assert payload.context == "crear modulo auth.py"

    def test_to_intent_payload_invalid_operation(self, agent):
        """Should default to SEARCH for invalid operations."""
        output = IntentOutput(operation="INVALID", goal="FEATURE_ADD")
        payload = agent.to_intent_payload(output)
        assert payload.op == "SEARCH"

    def test_to_intent_payload_scrap_query(self, agent):
        """Should generate scrap_query for CREATE/OPTIMIZE/REFACTOR."""
        output = IntentOutput(operation="CREATE", goal="FEATURE_ADD", language="python")
        payload = agent.to_intent_payload(output)
        assert payload.scrap_query != ""

    def test_to_intent_payload_no_scrap_query_for_search(self, agent):
        """Should not generate scrap_query for SEARCH/EXPLAIN/ANALYZE."""
        output = IntentOutput(operation="SEARCH", goal="FEATURE_ADD", language="python")
        payload = agent.to_intent_payload(output)
        assert payload.scrap_query == ""


# ============================================================
#  Test: build_prompt + parse_response (LLM path)
# ============================================================

class TestIntentAgentLLMPath:
    """Tests for the LLM prompt building and response parsing."""

    def test_build_prompt_with_intent_input(self, agent):
        """Should build system + user prompt from IntentInput."""
        system, user = agent.build_prompt(IntentInput(
            message="crear modulo auth.py", context="previous conversation"
        ))
        assert "intent classification" in system.lower()
        assert "crear modulo auth.py" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("fix bug in login")
        assert "intent classification" in system.lower()
        assert "fix bug in login" in user

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"operation":"CREATE","goal":"FEATURE_ADD","target":"auth.py","language":"python","entities":{},"template_type":"api","criticality":"standard","confidence":0.9}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "CREATE"
        assert result.goal == "FEATURE_ADD"
        assert result.target == "auth.py"
        assert result.confidence == 0.9
        assert result.source == "llm"

    def test_parse_response_markdown_json(self, agent):
        """Should parse JSON from markdown code block."""
        raw = '```json\n{"operation":"DEBUG","goal":"BUG_FIX","target":"login.py","language":"python","confidence":0.75}\n```'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "DEBUG"
        assert result.goal == "BUG_FIX"

    def test_parse_response_invalid_operation(self, agent):
        """Should default invalid operations to SEARCH."""
        raw = '{"operation":"INVALID_OP","goal":"FEATURE_ADD","confidence":0.5}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "SEARCH"

    def test_parse_response_free_text(self, agent):
        """Should parse free text when no JSON is found."""
        raw = "The operation is CREATE and the goal is FEATURE_ADD"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "CREATE"
        assert result.goal == "FEATURE_ADD"

    def test_parse_response_empty(self, agent):
        """Should handle empty or unparseable response."""
        raw = "xyzzy foo bar baz"
        result = agent.parse_response(raw, None)
        # Free text fallback should still return something
        assert result is not None


# ============================================================
#  Test: SemanticEngine Integration
# ============================================================

class TestIntentAgentSemanticEngine:
    """Tests for SemanticEngine integration in fallback path."""

    def test_semantic_engine_classification(self, agent_with_semantic):
        """Should use SemanticEngine when available and confident."""
        agent, mock_semantic = agent_with_semantic
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert result.confidence > 0.3

    def test_semantic_engine_low_confidence_falls_to_tfidf(self, agent_with_semantic):
        """Should fall back to TF-IDF when SemanticEngine has low confidence."""
        agent, mock_semantic = agent_with_semantic
        mock_semantic.classify_intent.return_value = MagicMock(
            operation="SEARCH",
            goal="FEATURE_ADD",
            confidence=0.1,  # Too low
            source="embedding",
        )
        result = agent.fallback(IntentInput(message="crear modulo"))
        # Should still classify, but may differ from SemanticEngine
        assert result.operation in VALID_OPERATIONS

    def test_semantic_engine_unavailable(self, agent):
        """Should use TF-IDF when SemanticEngine is not loaded."""
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = False
        agent.wire(semantic_engine=mock_semantic)
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.source == "fallback"


# ============================================================
#  Test: SmartMemory Integration
# ============================================================

class TestIntentAgentSmartMemory:
    """Tests for SmartMemory cache integration."""

    def test_smart_memory_cache_hit(self, agent_with_memory):
        """Should return cached result from SmartMemory."""
        agent, mock_memory = agent_with_memory
        mock_memory.check_cache.return_value = {
            "operation": "CREATE",
            "goal": "FEATURE_ADD",
            "target": "auth.py",
            "language": "python",
            "importance": 0.8,
        }
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert result.source == "fallback"  # SmartMemory is part of fallback

    def test_smart_memory_save_on_result(self, agent_with_memory):
        """Should save classification result to SmartMemory."""
        agent, mock_memory = agent_with_memory
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        # SmartMemory.save_to_cache should have been called
        assert mock_memory.save_to_cache.called

    def test_smart_memory_failure_graceful(self, agent):
        """Should handle SmartMemory failures gracefully."""
        mock_memory = MagicMock()
        mock_memory.check_cache.side_effect = Exception("DB error")
        agent.wire(smart_memory=mock_memory)
        # Should not raise, should fall through to TF-IDF
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation in VALID_OPERATIONS


# ============================================================
#  Test: classify_with_runner (full AgentRunner integration)
# ============================================================

class TestIntentAgentWithRunner:
    """Tests for classify_with_runner using AgentRunner."""

    def test_runner_llm_success(self, agent):
        """Should use LLM result when runner succeeds."""
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
        assert result.source == "llm"

    def test_runner_failure_uses_fallback(self, agent):
        """Should use fallback when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error", error="LLM timeout"
        )
        result = agent.classify_with_runner(mock_runner, "crear modulo auth.py")
        assert result.operation == "CREATE"
        assert result.source == "fallback"
