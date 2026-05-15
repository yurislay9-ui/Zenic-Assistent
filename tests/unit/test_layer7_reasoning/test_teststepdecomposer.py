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



class TestStepDecomposer:
    """A36: Break a problem into ordered reasoning steps."""

    def setup_method(self):
        self.decomposer = StepDecomposer()

    def test_api_decomposition(self):
        """API type should produce API-specific steps."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert isinstance(result, DecomposedSteps)
        assert len(result.steps) > 0
        assert any("endpoint" in s.description.lower() for s in result.steps)

    def test_auth_decomposition(self):
        """Auth type should produce auth-specific steps."""
        result = self.decomposer.execute(ProblemType(type="auth"))
        assert len(result.steps) > 0
        assert any("auth" in s.description.lower() or "credential" in s.description.lower()
                    for s in result.steps)

    def test_database_decomposition(self):
        """Database type should produce database-specific steps."""
        result = self.decomposer.execute(ProblemType(type="database"))
        assert len(result.steps) > 0
        assert any("schema" in s.description.lower() or "database" in s.description.lower()
                    for s in result.steps)

    def test_automation_decomposition(self):
        """Automation type should produce automation-specific steps."""
        result = self.decomposer.execute(ProblemType(type="automation"))
        assert len(result.steps) > 0
        assert any("trigger" in s.description.lower() for s in result.steps)

    def test_generic_decomposition(self):
        """Unknown type should produce generic steps."""
        result = self.decomposer.execute(ProblemType(type="general"))
        assert len(result.steps) > 0
        # Generic template should have standard steps
        assert result.steps[0].step_number == 1

    def test_dict_input_with_type(self):
        """Dict with 'problem_type' key should work."""
        result = self.decomposer.execute({"problem_type": "invoice"})
        assert len(result.steps) > 0

    def test_dict_input_with_problem_type_object(self):
        """Dict with ProblemType object should work."""
        result = self.decomposer.execute({"problem_type": ProblemType(type="crm")})
        assert len(result.steps) > 0

    def test_string_input_auto_detects(self):
        """String input should auto-detect and decompose."""
        result = self.decomposer.execute("Build an API endpoint")
        assert len(result.steps) > 0

    def test_steps_are_numbered(self):
        """Steps should be numbered sequentially."""
        result = self.decomposer.execute(ProblemType(type="api"))
        for i, step in enumerate(result.steps):
            assert step.step_number == i + 1

    def test_dependencies_not_empty(self):
        """Dependencies should be populated for non-trivial templates."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert len(result.dependencies) > 0

    def test_order_matches_step_numbers(self):
        """Order should match step numbers."""
        result = self.decomposer.execute(ProblemType(type="auth"))
        assert result.order == [s.step_number for s in result.steps]

    def test_source_is_deterministic(self):
        """Source should be deterministic."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert result.source == "deterministic"

    def test_decompose_with_context(self):
        """decompose_with_context should inject context into first step."""
        result = self.decomposer.decompose_with_context(
            ProblemType(type="api"), context="Previous API used FastAPI"
        )
        assert len(result.steps) > 0
        assert "Previous API" in result.steps[0].description

    def test_max_steps_limit(self):
        """Steps should be capped at MAX_STEPS."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert len(result.steps) <= 8

    def test_fallback_returns_3_steps(self):
        """Fallback should return generic 3-step process."""
        result = self.decomposer.fallback(None)
        assert len(result.steps) == 3
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A37 TemplateReasoner Tests
# ═══════════════════════════════════════════════════════════

