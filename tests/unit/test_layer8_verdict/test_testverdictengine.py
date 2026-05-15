"""
Tests for Layer 8: Verdict Engine agents (A40-A43).

All 4 agents tested:
  - A40 DeterministicPipeline (7 deterministic tasks)
  - A41 EvidenceCollectorV18
  - A42 ConsensusResolverV18
  - A43 VerdictEngineV18
"""

import pytest

from src.core.agents.verdict import (
    DeterministicPipeline,
    EvidenceCollectorV18,
    ConsensusResolverV18,
    VerdictEngineV18,
)
from src.core.agents.schemas import (
    PipelineResult,
    Evidence,
    EvidenceType,
    ConsensusResult,
    Verdict,
    VerdictInput,
    VerdictOutput,
    SecurityResult,
    SyntaxResult,
    CriticalityResult,
    IntentResult,
    ValidationIssue,
)


# ======================================================================
# A40 DeterministicPipeline Tests
# ======================================================================



class TestVerdictEngine:
    """A43: Binary verdict engine -- the ONLY place AI is used."""

    def setup_method(self):
        self.engine = VerdictEngineV18()

    def test_consensus_clear_no_ai(self):
        consensus = ConsensusResult(
            verdict=Verdict.YES,
            confidence=0.9,
            needs_llm=False,
        )
        result = self.engine.execute({"consensus_result": consensus})
        assert isinstance(result, VerdictOutput)
        assert result.verdict == Verdict.YES
        assert result.llm_used is False
        assert result.source == "deterministic_consensus"

    def test_consensus_clear_no_verdict(self):
        consensus = ConsensusResult(
            verdict=Verdict.NO,
            confidence=0.9,
            needs_llm=False,
        )
        result = self.engine.execute({"consensus_result": consensus})
        assert result.verdict == Verdict.NO
        assert result.llm_used is False

    def test_no_model_returns_no(self):
        result = self.engine.execute({"question": "Is this safe?"})
        assert result.verdict == Verdict.NO
        assert result.source in ("fallback_no_model", "fallback_circuit_open")

    def test_parse_verdict_yes(self):
        assert VerdictEngineV18._parse_verdict_response("YES") == "YES"

    def test_parse_verdict_no(self):
        assert VerdictEngineV18._parse_verdict_response("NO") == "NO"

    def test_parse_verdict_yes_with_think(self):
        response = " YES"
        assert VerdictEngineV18._parse_verdict_response(response) == "YES"

    def test_parse_verdict_no_with_think(self):
        response = " NO"
        assert VerdictEngineV18._parse_verdict_response(response) == "NO"

    def test_parse_verdict_si(self):
        assert VerdictEngineV18._parse_verdict_response("SI") == "YES"

    def test_parse_verdict_ambiguous(self):
        assert VerdictEngineV18._parse_verdict_response("MAYBE") is None

    def test_parse_verdict_empty(self):
        assert VerdictEngineV18._parse_verdict_response("") is None

    def test_parse_verdict_none(self):
        assert VerdictEngineV18._parse_verdict_response(None) is None

    def test_parse_verdict_yes_punctuation(self):
        assert VerdictEngineV18._parse_verdict_response("YES.") == "YES"

    def test_verdict_input_object(self):
        vinput = VerdictInput(question="Should this be approved?")
        result = self.engine.execute(vinput)
        assert isinstance(result, VerdictOutput)

    def test_wire_mini_ai(self):
        self.engine.wire_mini_ai(None)

    def test_verdict_stats_initial(self):
        stats = self.engine.verdict_stats
        assert stats["total_verdicts"] == 0
        assert "yes_count" in stats
        assert "no_count" in stats

    def test_fallback_returns_no(self):
        result = self.engine.fallback(None)
        assert result.verdict == Verdict.NO
        assert result.confidence < 0.5
        assert result.source == "fallback"
        assert result.llm_used is False


# ======================================================================
# Integration: Full Verdict Pipeline Test
# ======================================================================

