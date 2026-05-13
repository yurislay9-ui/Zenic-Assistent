"""
Tests for SurgicalAgent signal fusion, calibration, and 4 cables.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.surgical_agent import SurgicalAgent, VALID_OPERATIONS
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Test: IntentOutput → IntentPayload Conversion
# ============================================================

class TestSurgicalAgentConversion:
    """Tests for IntentOutput to IntentPayload conversion (pipeline compat)."""

    def test_to_intent_payload_basic(self, agent):
        output = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            target="auth.py", language="python",
            confidence=0.8, source="llm",
        )
        payload = agent.to_intent_payload(output, context="crear modulo auth.py")
        assert payload.op == "CREATE"
        assert payload.goal == "FEATURE_ADD"
        assert payload.target == "auth.py"
        assert payload.confidence == 0.8

    def test_to_intent_payload_invalid_operation(self, agent):
        output = IntentOutput(operation="INVALID", goal="FEATURE_ADD")
        payload = agent.to_intent_payload(output)
        assert payload.op == "SEARCH"

    def test_to_intent_payload_scrap_query(self, agent):
        output = IntentOutput(operation="CREATE", goal="FEATURE_ADD", language="python")
        payload = agent.to_intent_payload(output)
        assert payload.scrap_query != ""


# ============================================================
#  Test: Multi-Signal Fusion
# ============================================================

class TestSurgicalAgentFusion:
    """Tests for multi-signal fusion (core F2 innovation)."""

    def test_fusion_concordance_boosts_confidence(self, agent):
        """When TF-IDF and Semantic fully agree (op+goal), confidence should be higher than individual."""
        tfidf = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            confidence=0.5, source="tfidf",
        )
        semantic = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            confidence=0.5, source="semantic",
        )
        fused = agent._fuse_signals(tfidf, semantic)
        assert fused.confidence > 0.5

    def test_fusion_discrepancy_reduces_confidence(self, agent):
        """When signals disagree, confidence should be reduced."""
        tfidf = IntentOutput(
            operation="SEARCH", goal="FEATURE_ADD",
            confidence=0.3, source="tfidf",
        )
        semantic = IntentOutput(
            operation="DEBUG", goal="BUG_FIX",
            confidence=0.4, source="semantic",
        )
        fused = agent._fuse_signals(tfidf, semantic)
        assert fused.confidence < semantic.confidence

    def test_fusion_secondary_none_preserves_primary(self, agent):
        """Without secondary signal, primary is preserved with calibration."""
        primary = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            confidence=0.5, source="tfidf",
        )
        fused = agent._fuse_signals(primary, None)
        assert fused.operation == "CREATE"
        assert fused.goal == "FEATURE_ADD"


# ============================================================
#  Test: Adaptive Calibration
# ============================================================

class TestSurgicalAgentCalibration:
    """Tests for adaptive calibration system."""

    def test_initial_calibration_is_neutral(self, agent):
        """New agent should have neutral calibration factor (1.0)."""
        factor = agent.get_calibration_factor("CREATE")
        assert factor == 1.0

    def test_good_accuracy_boosts_factor(self, agent):
        """After correct classifications, calibration should increase."""
        for _ in range(5):
            agent.report_accuracy("CREATE", was_correct=True)
        factor = agent.get_calibration_factor("CREATE")
        assert factor > 1.0

    def test_bad_accuracy_reduces_factor(self, agent):
        """After incorrect classifications, calibration should decrease."""
        for _ in range(5):
            agent.report_accuracy("CREATE", was_correct=False)
        factor = agent.get_calibration_factor("CREATE")
        assert factor < 1.0

    def test_calibration_is_per_operation(self, agent):
        """Calibration for one operation should not affect others."""
        for _ in range(5):
            agent.report_accuracy("CREATE", was_correct=True)
        create_factor = agent.get_calibration_factor("CREATE")
        debug_factor = agent.get_calibration_factor("DEBUG")
        assert create_factor > debug_factor


# ============================================================
#  Test: 4 Cables
# ============================================================

class TestSurgicalAgentCables:
    """Tests for the 4 classification cables."""

    def test_cable_memory_hit(self, agent_with_memory):
        """CABLE 1: SmartMemory cache hit returns immediately."""
        agent, mock_memory = agent_with_memory
        mock_memory.check_cache.return_value = {
            "operation": "CREATE", "goal": "FEATURE_ADD",
            "target": "auth.py", "language": "python",
            "importance": 0.8,
        }
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert result.source == "cache"

    def test_cable_memory_miss_falls_through(self, agent_with_memory):
        """CABLE 1 miss should fall through to other cables."""
        agent, mock_memory = agent_with_memory
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert result.operation == "CREATE"

    def test_cable_semantic_high_confidence(self, agent_with_semantic):
        """CABLE 2: SemanticEngine with high confidence."""
        agent, mock_semantic = agent_with_semantic
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert "+" in result.source or result.source in ("tfidf", "semantic")

    def test_cable_tfidf_always_works(self, agent):
        """CABLE 4: TF-IDF should always produce a result."""
        result = agent.fallback(IntentInput(message="hacer algo"))
        assert result is not None
        assert result.operation in VALID_OPERATIONS
        assert result.source == "tfidf"
