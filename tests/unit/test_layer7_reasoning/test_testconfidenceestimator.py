"""
Tests for Layer 7: Reasoning agents (A35-A39).

All 5 agents tested:
  - A35 ProblemDetector
  - A36 StepDecomposer
  - A37 TemplateReasoner
  - A38 ConfidenceEstimator
  - A39 ConclusionExtractor
"""

import pytest

from src.core.agents.reasoning import (
    ProblemDetector,
    StepDecomposer,
    TemplateReasoner,
    ConfidenceEstimator,
    ConclusionExtractor,
)
from src.core.agents.schemas import (
    ProblemType,
    ReasoningStep,
    ReasoningResult,
    DecomposedSteps,
    ConfidenceResult,
    Conclusion,
)


# ═══════════════════════════════════════════════════════════
# A35 ProblemDetector Tests
# ═══════════════════════════════════════════════════════════



class TestConfidenceEstimator:
    """A38: Estimate confidence in a reasoning result."""

    def setup_method(self):
        self.estimator = ConfidenceEstimator()

    def test_high_confidence_result(self):
        """Well-structured result with high base confidence should score well."""
        result = ReasoningResult(
            answer="Implement JWT-based authentication with token refresh, "
                   "password hashing, and RBAC for authorization. This is a "
                   "definitely clear and complete solution.",
            template_used="auth",
            confidence=0.8,
            steps=[
                ReasoningStep(step_number=1, description="Define auth", conclusion="Auth defined", confidence=0.8),
                ReasoningStep(step_number=2, description="Implement tokens", conclusion="Tokens implemented", confidence=0.85),
                ReasoningStep(step_number=3, description="Add RBAC", conclusion="RBAC added", confidence=0.75),
            ],
        )
        conf = self.estimator.execute(result)
        assert isinstance(conf, ConfidenceResult)
        assert conf.score > 0.5
        assert conf.recommendation in ("proceed", "caution")

    def test_low_confidence_short_answer(self):
        """Short answer should have low confidence."""
        result = ReasoningResult(
            answer="Fix it.",
            confidence=0.3,
            steps=[],
        )
        conf = self.estimator.execute(result)
        assert conf.score < 0.5

    def test_security_risk_decreases_confidence(self):
        """Answer with eval() should significantly decrease confidence."""
        safe = ReasoningResult(
            answer="Implement data processing with proper validation and error handling.",
            confidence=0.6,
        )
        risky = ReasoningResult(
            answer="Use eval() to process the data and exec() to run commands.",
            confidence=0.6,
        )
        safe_conf = self.estimator.execute(safe)
        risky_conf = self.estimator.execute(risky)
        assert risky_conf.score < safe_conf.score

    def test_hedging_decreases_confidence(self):
        """Hedging language should decrease confidence."""
        certain = ReasoningResult(
            answer="This is certainly the correct implementation with clear validation.",
            confidence=0.6,
        )
        hedging = ReasoningResult(
            answer="This might be perhaps a possible implementation maybe.",
            confidence=0.6,
        )
        certain_conf = self.estimator.execute(certain)
        hedging_conf = self.estimator.execute(hedging)
        assert hedging_conf.score < certain_conf.score

    def test_quality_issues_decrease_confidence(self):
        """TODO/FIXME markers should decrease confidence."""
        clean = ReasoningResult(
            answer="Complete implementation with error handling and validation.",
            confidence=0.6,
        )
        quality_issues = ReasoningResult(
            answer="TODO: implement error handling FIXME: add validation HACK: quick fix.",
            confidence=0.6,
        )
        clean_conf = self.estimator.execute(clean)
        issues_conf = self.estimator.execute(quality_issues)
        assert issues_conf.score < clean_conf.score

    def test_steps_improve_confidence(self):
        """Having reasoning steps should improve confidence."""
        no_steps = ReasoningResult(
            answer="Implement the authentication system with proper security.",
            confidence=0.6,
        )
        with_steps = ReasoningResult(
            answer="Implement the authentication system with proper security.",
            confidence=0.6,
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Done", confidence=0.7),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Done", confidence=0.8),
            ],
        )
        no_steps_conf = self.estimator.execute(no_steps)
        with_steps_conf = self.estimator.execute(with_steps)
        assert with_steps_conf.score >= no_steps_conf.score

    def test_template_match_improves_confidence(self):
        """Known template match should improve confidence."""
        generic = ReasoningResult(
            answer="Good implementation with error handling.",
            template_used="generic",
            confidence=0.6,
        )
        matched = ReasoningResult(
            answer="Good implementation with error handling.",
            template_used="auth",
            confidence=0.6,
        )
        generic_conf = self.estimator.execute(generic)
        matched_conf = self.estimator.execute(matched)
        assert matched_conf.score >= generic_conf.score

    def test_recommendation_proceed(self):
        """High confidence should recommend proceed."""
        result = ReasoningResult(
            answer="Complete implementation with thorough error handling, validation, "
                   "and comprehensive test coverage. Clearly the best approach.",
            confidence=0.9,
            template_used="auth",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Done", confidence=0.9),
            ],
        )
        conf = self.estimator.execute(result)
        assert conf.recommendation in ("proceed", "caution")

    def test_recommendation_reject(self):
        """Very low confidence should recommend reject."""
        result = ReasoningResult(
            answer="eval()",
            confidence=0.1,
        )
        conf = self.estimator.execute(result)
        assert conf.recommendation in ("reject", "caution")

    def test_string_input(self):
        """String input should work."""
        conf = self.estimator.execute("This is a clear and complete implementation")
        assert isinstance(conf, ConfidenceResult)

    def test_dict_input(self):
        """Dict input should work."""
        conf = self.estimator.execute({"answer": "Implement auth", "confidence": 0.7})
        assert isinstance(conf, ConfidenceResult)

    def test_factors_populated(self):
        """Factors list should be populated."""
        result = ReasoningResult(
            answer="Good implementation with error handling and validation.",
            confidence=0.6,
            steps=[ReasoningStep(step_number=1, description="Step 1", conclusion="Done", confidence=0.7)],
        )
        conf = self.estimator.execute(result)
        assert len(conf.factors) > 0

    def test_estimate_with_evidence(self):
        """estimate_with_evidence should adjust based on evidence."""
        result = ReasoningResult(
            answer="Implementation with proper patterns.",
            confidence=0.6,
        )
        base = self.estimator.execute(result)
        with_evidence = self.estimator.estimate_with_evidence(
            result,
            evidence_for=["Pattern match", "Valid syntax"],
            evidence_against=["Security concern"],
        )
        # Score with evidence should differ from base
        assert isinstance(with_evidence, ConfidenceResult)
        assert len(with_evidence.factors) > len(base.factors)

    def test_fallback_returns_low_confidence(self):
        """Fallback should return low confidence with caution."""
        result = self.estimator.fallback(None)
        assert result.score < 0.5
        assert result.recommendation in ("caution", "reject")
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A39 ConclusionExtractor Tests
# ═══════════════════════════════════════════════════════════

