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



class TestProblemDetector:
    """A35: Detect the type of problem from query text."""

    def setup_method(self):
        self.detector = ProblemDetector()

    def test_api_problem(self):
        """'api' should detect api type."""
        result = self.detector.execute("Create a REST API for user management")
        assert isinstance(result, ProblemType)
        assert result.type == "api"

    def test_auth_problem(self):
        """'auth' should detect auth type."""
        result = self.detector.execute("Implement authentication and login system")
        assert result.type == "auth"

    def test_database_problem(self):
        """'database' should detect database type."""
        result = self.detector.execute("Design the database schema and migration")
        assert result.type == "database"

    def test_invoice_problem(self):
        """'invoice' should detect invoice type."""
        result = self.detector.execute("Create an invoice and billing system")
        assert result.type == "invoice"

    def test_inventory_problem(self):
        """'inventario' should detect inventory type."""
        result = self.detector.execute("Gestionar inventario y stock de productos")
        assert result.type == "inventory"

    def test_crm_problem(self):
        """'crm' should detect crm type."""
        result = self.detector.execute("Build a CRM for customer pipeline management")
        assert result.type == "crm"

    def test_automation_problem(self):
        """'automation' should detect automation type."""
        result = self.detector.execute("Create an automation with webhook trigger")
        assert result.type == "automation"

    def test_general_problem(self):
        """No matching keywords should return general type."""
        result = self.detector.execute("Process some data")
        assert result.type == "general"

    def test_empty_input(self):
        """Empty input should return general with 0 complexity."""
        result = self.detector.execute("")
        assert result.type == "general"
        assert result.complexity == 0.0

    def test_dict_input_query(self):
        """Dict with 'query' key should work."""
        result = self.detector.execute({"query": "Build an auth system"})
        assert result.type == "auth"

    def test_dict_input_text(self):
        """Dict with 'text' key should work."""
        result = self.detector.execute({"text": "Design the database schema"})
        assert result.type == "database"

    def test_problem_type_object_input(self):
        """ProblemType object should be handled."""
        pt = ProblemType(type="api")
        result = self.detector.execute(pt)
        # When passing ProblemType, it should still detect from its type
        assert isinstance(result, ProblemType)

    def test_subtype_jwt(self):
        """Auth with 'jwt' should detect jwt subtype."""
        result = self.detector.execute("Implement JWT token authentication")
        assert result.type == "auth"
        assert result.subtype == "jwt"

    def test_subtype_rest(self):
        """API with 'rest' should detect rest subtype."""
        result = self.detector.execute("Create REST API endpoints")
        assert result.type == "api"
        assert result.subtype == "rest"

    def test_subtype_scheduled(self):
        """Automation with 'schedule' should detect scheduled subtype."""
        result = self.detector.execute("Create scheduled automation daily")
        assert result.type == "automation"
        assert result.subtype == "scheduled"

    def test_complexity_short_query(self):
        """Short query should have low complexity."""
        result = self.detector.execute("Fix bug")
        assert result.complexity < 0.5

    def test_complexity_long_query(self):
        """Long query with multiple concepts should have high complexity."""
        result = self.detector.execute(
            "Build a microservice with API, database, authentication, "
            "caching, async processing and distributed scaling"
        )
        assert result.complexity > 0.5

    def test_complexity_connectors(self):
        """Multiple connectors (and, but, however) should increase complexity."""
        simple = self.detector.execute("Fix bug in code")
        complex_q = self.detector.execute("Fix bug in code and add tests but also handle edge cases")
        assert complex_q.complexity > simple.complexity

    def test_complexity_tech_terms(self):
        """Technical terms should increase complexity."""
        simple = self.detector.execute("Create a simple feature")
        tech = self.detector.execute("Create API with database, caching and middleware")
        assert tech.complexity > simple.complexity

    def test_auth_priority_over_api(self):
        """Auth should take priority over API (per TYPE_PRIORITY)."""
        result = self.detector.execute("Build an API with auth login")
        assert result.type == "auth"

    def test_detect_all_types(self):
        """detect_all_types should return all matching types."""
        results = self.detector.detect_all_types("Build an API with auth and database")
        types = [t for t, _ in results]
        assert "api" in types
        assert "auth" in types
        assert "database" in types

    def test_detect_all_types_empty(self):
        """detect_all_types with empty input should return empty list."""
        results = self.detector.detect_all_types("")
        assert results == []

    def test_fallback_returns_general(self):
        """Fallback should return general type."""
        result = self.detector.fallback(None)
        assert result.type == "general"
        assert result.source == "fallback"
        assert result.complexity == 0.5


# ═══════════════════════════════════════════════════════════
# A36 StepDecomposer Tests
# ═══════════════════════════════════════════════════════════

