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



class TestEvidenceCollector:
    """A41: Collect evidence for/against a decision."""

    def setup_method(self):
        self.collector = EvidenceCollectorV18()

    def test_safe_security_evidence(self):
        result = self.collector.execute({
            "security_result": SecurityResult(safe=True),
        })
        assert len(result) > 0
        assert any(e.favors == "YES" for e in result)

    def test_unsafe_security_evidence(self):
        result = self.collector.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(code="eval_call", message="eval() detected")],
                risk_score=0.8,
            ),
        })
        assert len(result) > 0
        assert any(e.favors == "NO" for e in result)

    def test_valid_syntax_evidence(self):
        result = self.collector.execute({
            "syntax_result": SyntaxResult(valid=True),
        })
        assert any(e.favors == "YES" for e in result)

    def test_invalid_syntax_evidence(self):
        result = self.collector.execute({
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(code="syntax_error", message="Invalid syntax")],
            ),
        })
        assert any(e.favors == "NO" for e in result)

    def test_low_criticality_evidence(self):
        result = self.collector.execute({
            "criticality_result": CriticalityResult(level=1, confidence=0.8),
        })
        assert any(e.favors == "YES" for e in result)

    def test_high_criticality_evidence(self):
        result = self.collector.execute({
            "criticality_result": CriticalityResult(level=3, confidence=0.9),
        })
        assert any(e.favors == "NO" for e in result)

    def test_high_intent_confidence(self):
        result = self.collector.execute({
            "intent_result": IntentResult(confidence=0.8),
        })
        assert any(e.favors == "YES" for e in result)

    def test_low_intent_confidence(self):
        result = self.collector.execute({
            "intent_result": IntentResult(confidence=0.2),
        })
        assert any(e.favors == "NO" for e in result)

    def test_combined_evidence(self):
        result = self.collector.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
            "criticality_result": CriticalityResult(level=1, confidence=0.8),
        })
        assert len(result) >= 3

    def test_non_dict_input_returns_empty(self):
        result = self.collector.execute("invalid input")
        assert result == []

    def test_empty_dict_returns_empty(self):
        result = self.collector.execute({})
        assert result == []

    def test_evidence_types_are_set(self):
        result = self.collector.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
        })
        types = {e.evidence_type for e in result}
        assert EvidenceType.SECURITY_CHECK in types
        assert EvidenceType.SYNTAX_VALID in types

    def test_fallback_returns_empty(self):
        result = self.collector.fallback(None)
        assert result == []


# ======================================================================
# A42 ConsensusResolverV18 Tests
# ======================================================================

