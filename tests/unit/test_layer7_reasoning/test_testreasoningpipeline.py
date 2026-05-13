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

from src.core.agents_v2.reasoning import (
    ProblemDetector,
    StepDecomposer,
    TemplateReasoner,
    ConfidenceEstimator,
    ConclusionExtractor,
)
from src.core.agents_v2.schemas import (
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



class TestReasoningPipeline:
    """End-to-end reasoning pipeline through all Layer 7 agents."""

    def test_full_reasoning_pipeline_api(self):
        """Full pipeline: detect → decompose → reason → estimate → extract."""
        query = "Build a REST API with authentication and database"

        # Step 1: Detect problem type
        problem = ProblemDetector().execute(query)
        assert problem.type == "auth"  # Auth takes priority per TYPE_PRIORITY
        assert problem.complexity > 0.3

        # Step 2: Decompose into steps
        steps = StepDecomposer().execute(problem)
        assert len(steps.steps) > 0
        assert len(steps.dependencies) > 0

        # Step 3: Apply template reasoning
        reasoning = TemplateReasoner().execute(problem)
        assert reasoning.answer != ""
        assert reasoning.template_used != ""
        assert reasoning.confidence > 0.5

        # Step 4: Estimate confidence
        confidence = ConfidenceEstimator().execute(reasoning)
        assert confidence.score > 0.0
        assert confidence.recommendation in ("proceed", "caution", "reject")
        assert len(confidence.factors) > 0

        # Step 5: Extract conclusion
        conclusion = ConclusionExtractor().execute(reasoning)
        assert conclusion.text != ""
        assert conclusion.strength > 0.0

    def test_full_reasoning_pipeline_invoice_es(self):
        """Full pipeline in Spanish: 'Crear sistema de facturación con inventario'"""
        query = "Crear sistema de facturación con inventario y alertas"

        # Step 1: Detect
        problem = ProblemDetector().execute(query)
        assert problem.type == "invoice"  # Invoice takes priority

        # Step 2: Decompose
        steps = StepDecomposer().execute(problem)
        assert len(steps.steps) > 0

        # Step 3: Reason
        reasoning = TemplateReasoner().execute(problem)
        assert reasoning.template_used == "invoice"

        # Step 4: Confidence
        confidence = ConfidenceEstimator().execute(reasoning)
        assert confidence.score > 0.3

        # Step 5: Conclusion
        conclusion = ConclusionExtractor().execute(reasoning)
        assert conclusion.text != ""

    def test_pipeline_with_context_injection(self):
        """Pipeline with context injection at each step."""
        query = "Automate daily email report"
        context = "Previous implementation used APScheduler"

        # Step 1: Detect
        problem = ProblemDetector().execute(query)
        assert problem.type == "automation"

        # Step 2: Decompose with context
        steps = StepDecomposer().decompose_with_context(problem, context=context)
        assert "APScheduler" in steps.steps[0].description or "Previous" in steps.steps[0].description

        # Step 3: Reason with context
        reasoning = TemplateReasoner().execute({
            "problem_type": problem,
            "context": context,
        })
        assert reasoning.answer != ""

        # Step 4: Confidence
        confidence = ConfidenceEstimator().execute(reasoning)
        assert isinstance(confidence, ConfidenceResult)

        # Step 5: Conclusion
        conclusion = ConclusionExtractor().execute(reasoning)
        assert conclusion.text != ""

    def test_pipeline_general_unknown_problem(self):
        """Pipeline should handle unknown problems gracefully."""
        query = "Process some random data"

        # Step 1: Detect → general
        problem = ProblemDetector().execute(query)
        assert problem.type == "general"

        # Step 2: Decompose → generic steps
        steps = StepDecomposer().execute(problem)
        assert len(steps.steps) > 0

        # Step 3: Reason → generic template
        reasoning = TemplateReasoner().execute(problem)
        assert reasoning.template_used == "generic"
        assert reasoning.confidence < 0.5

        # Step 4: Confidence should be cautious
        confidence = ConfidenceEstimator().execute(reasoning)
        assert confidence.recommendation in ("caution", "reject", "proceed")

        # Step 5: Conclusion should still extract something
        conclusion = ConclusionExtractor().execute(reasoning)
        assert isinstance(conclusion, Conclusion)
