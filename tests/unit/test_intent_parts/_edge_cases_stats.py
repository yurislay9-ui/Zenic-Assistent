"""Tests for IntentAgent edge cases and stats tracking."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.intent_agent import IntentAgent, VALID_OPERATIONS
from src.core.agents.schemas import IntentInput


# ============================================================
#  Test: Edge Cases
# ============================================================

class TestIntentAgentEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_message(self, agent):
        """Should handle empty messages gracefully."""
        result = agent.fallback(IntentInput(message=""))
        assert result is not None
        assert result.operation in VALID_OPERATIONS

    def test_very_long_message(self, agent):
        """Should handle very long messages without crashing."""
        long_msg = "crear " + "modulo " * 500
        result = agent.fallback(IntentInput(message=long_msg))
        assert result is not None

    def test_special_characters(self, agent):
        """Should handle special characters in messages."""
        result = agent.fallback(IntentInput(message="crear módulo auth.py con ñ y áéíóú"))
        assert result is not None

    def test_message_with_only_code(self, agent):
        """Should handle messages that are mostly code."""
        result = agent.fallback(IntentInput(
            message="def process_data(data):\n    return data.filter(lambda x: x > 0)"
        ))
        assert result is not None

    def test_confidence_always_in_range(self, agent):
        """Confidence should always be between 0 and 1."""
        for msg in ["crear", "debug error", "fix bug", "hello world", ""]:
            result = agent.fallback(IntentInput(message=msg))
            assert 0.0 <= result.confidence <= 1.0

    def test_fallback_confidence_is_low(self, agent):
        """Fallback confidence should be in the 0-0.5 range."""
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.confidence <= 0.5

    def test_multiple_operations_in_message(self, agent):
        """Should pick the best matching operation when multiple match."""
        result = agent.fallback(IntentInput(message="debug y crear modulo"))
        assert result.operation in VALID_OPERATIONS


# ============================================================
#  Test: Stats Tracking
# ============================================================

class TestIntentAgentStats:
    """Tests for agent statistics tracking."""

    def test_initial_stats(self, agent):
        """Should have zero stats initially."""
        stats = agent.stats
        assert stats["name"] == "intent"
        assert stats["total_calls"] == 0

    def test_stats_after_fallback(self, agent):
        """Should track fallback calls."""
        agent.fallback(IntentInput(message="crear modulo"))
        stats = agent.stats
        assert stats["total_calls"] >= 1

    def test_wire_updates_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        agent.wire(semantic_engine=mock_semantic)
        assert agent._semantic_engine is mock_semantic

    def test_wire_updates_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_memory = MagicMock()
        agent.wire(smart_memory=mock_memory)
        assert agent._smart_memory is mock_memory
