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



class TestConsensusResolver:
    """A42: Resolve evidence into consensus or flag for AI."""

    def setup_method(self):
        self.resolver = ConsensusResolverV18()

    def test_unanimous_yes(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.7),
        ]
        result = self.resolver.execute(evidence)
        assert isinstance(result, ConsensusResult)
        assert result.verdict == Verdict.YES
        assert not result.needs_llm
        assert result.unanimous is True

    def test_unanimous_no(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="NO", weight=0.8),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.6),
        ]
        result = self.resolver.execute(evidence)
        assert result.verdict == Verdict.NO
        assert not result.needs_llm

    def test_security_veto(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SECURITY_CHECK, favors="NO", weight=0.9),
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.7),
        ]
        result = self.resolver.execute(evidence)
        assert result.verdict == Verdict.NO
        assert result.source == "deterministic_veto"
        assert not result.needs_llm

    def test_sandbox_veto(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SANDBOX_PASS, favors="NO", weight=0.8),
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.9),
        ]
        result = self.resolver.execute(evidence)
        assert result.verdict == Verdict.NO
        assert result.source == "deterministic_veto"

    def test_security_veto_low_weight_not_vetoed(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SECURITY_CHECK, favors="NO", weight=0.5),
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.9),
        ]
        result = self.resolver.execute(evidence)
        assert result.source != "deterministic_veto"

    def test_tie_requires_llm(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.5),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.5),
        ]
        result = self.resolver.execute(evidence)
        assert result.needs_llm is True

    def test_empty_evidence_needs_llm(self):
        result = self.resolver.execute([])
        assert result.needs_llm is True
        assert result.verdict == Verdict.NO

    def test_dict_input(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
        ]
        result = self.resolver.execute({"evidence": evidence})
        assert result.verdict == Verdict.YES

    def test_score_normalized(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.9),
        ]
        result = self.resolver.execute(evidence)
        assert -1.0 <= result.score <= 1.0

    def test_signals_count(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.6),
        ]
        result = self.resolver.execute(evidence)
        assert result.signals_count == 2

    def test_evidence_for_against_populated(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.3),
        ]
        result = self.resolver.execute(evidence)
        assert len(result.evidence_for) >= 1
        assert len(result.evidence_against) >= 1

    def test_fallback_returns_no(self):
        result = self.resolver.fallback(None)
        assert result.verdict == Verdict.NO
        assert result.confidence < 0.5
        assert result.source == "fallback"


# ======================================================================
# A43 VerdictEngineV18 Tests
# ======================================================================

