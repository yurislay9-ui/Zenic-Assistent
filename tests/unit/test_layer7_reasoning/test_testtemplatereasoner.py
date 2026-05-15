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



class TestTemplateReasoner:
    """A37: Apply template-based reasoning for known problem types."""

    def setup_method(self):
        self.reasoner = TemplateReasoner()

    def test_api_template(self):
        """API type should use API template."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert isinstance(result, ReasoningResult)
        assert result.template_used == "api"
        assert "API" in result.answer or "endpoint" in result.answer.lower()

    def test_auth_template(self):
        """Auth type should use auth template."""
        result = self.reasoner.execute(ProblemType(type="auth"))
        assert result.template_used == "auth"
        assert "JWT" in result.answer or "auth" in result.answer.lower()

    def test_database_template(self):
        """Database type should use database template."""
        result = self.reasoner.execute(ProblemType(type="database"))
        assert result.template_used == "database"
        assert "schema" in result.answer.lower() or "database" in result.answer.lower()

    def test_invoice_template(self):
        """Invoice type should use invoice template."""
        result = self.reasoner.execute(ProblemType(type="invoice"))
        assert result.template_used == "invoice"
        assert "invoice" in result.answer.lower()

    def test_inventory_template(self):
        """Inventory type should use inventory template."""
        result = self.reasoner.execute(ProblemType(type="inventory"))
        assert result.template_used == "inventory"

    def test_crm_template(self):
        """CRM type should use CRM template."""
        result = self.reasoner.execute(ProblemType(type="crm"))
        assert result.template_used == "crm"

    def test_automation_template(self):
        """Automation type should use automation template."""
        result = self.reasoner.execute(ProblemType(type="automation"))
        assert result.template_used == "automation"

    def test_logical_template(self):
        """Logical type should use logical template."""
        result = self.reasoner.execute(ProblemType(type="logical"))
        assert result.template_used == "logical"

    def test_arithmetic_template(self):
        """Arithmetic type should use arithmetic template."""
        result = self.reasoner.execute(ProblemType(type="arithmetic"))
        assert result.template_used == "arithmetic"

    def test_structural_template(self):
        """Structural type should use structural template."""
        result = self.reasoner.execute(ProblemType(type="structural"))
        assert result.template_used == "structural"

    def test_generic_template(self):
        """Unknown type should use generic template."""
        result = self.reasoner.execute(ProblemType(type="general"))
        assert result.template_used == "generic"
        assert result.confidence < 0.5

    def test_template_has_steps(self):
        """Template should produce reasoning steps."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert len(result.steps) > 0

    def test_step_conclusions_present(self):
        """Steps should have conclusions."""
        result = self.reasoner.execute(ProblemType(type="auth"))
        assert all(s.conclusion != "" for s in result.steps)

    def test_api_confidence(self):
        """API template should have reasonable confidence."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert result.confidence > 0.5

    def test_dict_input_with_type(self):
        """Dict with 'problem_type' key should work."""
        result = self.reasoner.execute({"problem_type": "api"})
        assert result.template_used == "api"

    def test_dict_input_with_problem_type_object(self):
        """Dict with ProblemType should work."""
        result = self.reasoner.execute({"problem_type": ProblemType(type="auth")})
        assert result.template_used == "auth"

    def test_string_input(self):
        """String input should auto-detect and apply template."""
        result = self.reasoner.execute("Build an authentication system")
        # Should detect auth and apply auth template
        assert isinstance(result, ReasoningResult)

    def test_context_enrichment(self):
        """Context should be appended to answer."""
        result = self.reasoner.execute({
            "problem_type": ProblemType(type="api"),
            "context": "Must use FastAPI framework",
        })
        assert "FastAPI" in result.answer or "context" in result.answer.lower()

    def test_list_available_templates(self):
        """list_available_templates should return all template names."""
        templates = self.reasoner.list_available_templates()
        assert "api" in templates
        assert "auth" in templates
        assert "database" in templates
        assert len(templates) >= 8

    def test_fallback_returns_generic(self):
        """Fallback should return generic template."""
        result = self.reasoner.fallback(None)
        assert result.template_used == "generic"
        assert result.source == "fallback"

    def test_source_is_deterministic(self):
        """Source should be deterministic."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert result.source == "deterministic"


# ═══════════════════════════════════════════════════════════
# A38 ConfidenceEstimator Tests
# ═══════════════════════════════════════════════════════════

