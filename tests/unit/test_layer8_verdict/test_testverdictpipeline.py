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



class TestVerdictPipeline:
    """End-to-end verdict pipeline through all Layer 8 agents."""

    def test_safe_code_verdict_pipeline(self):
        """Safe code should go through pipeline -> YES without AI."""
        pipeline = DeterministicPipeline()
        pipe_result = pipeline.execute({
            "text": "Create a validation function in utils.py",
        })
        assert pipe_result.classify is not None

        collector = EvidenceCollectorV18()
        evidence = collector.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
            "criticality_result": CriticalityResult(level=1, confidence=0.8),
            "intent_result": IntentResult(confidence=0.7),
        })
        assert len(evidence) > 0

        resolver = ConsensusResolverV18()
        consensus = resolver.execute(evidence)
        assert consensus.verdict == Verdict.YES
        assert not consensus.needs_llm

        engine = VerdictEngineV18()
        verdict = engine.execute({"consensus_result": consensus})
        assert verdict.verdict == Verdict.YES
        assert verdict.llm_used is False

    def test_unsafe_code_verdict_pipeline(self):
        """Unsafe code should trigger security veto -> NO without AI."""
        collector = EvidenceCollectorV18()
        evidence = collector.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(code="eval_call", message="eval() detected")],
                risk_score=0.9,
            ),
            "syntax_result": SyntaxResult(valid=True),
        })

        resolver = ConsensusResolverV18()
        consensus = resolver.execute(evidence)
        assert consensus.verdict == Verdict.NO
        assert consensus.source == "deterministic_veto"

        engine = VerdictEngineV18()
        verdict = engine.execute({"consensus_result": consensus})
        assert verdict.verdict == Verdict.NO
        assert verdict.llm_used is False

    def test_ambiguous_evidence_pipeline(self):
        """Ambiguous evidence should flag needs_llm=True."""
        evidence = [
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.5),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.5),
        ]

        resolver = ConsensusResolverV18()
        consensus = resolver.execute(evidence)
        assert consensus.needs_llm is True

        engine = VerdictEngineV18()
        verdict = engine.execute({"consensus_result": consensus})
        assert verdict.verdict == Verdict.NO
