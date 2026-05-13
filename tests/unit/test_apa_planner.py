"""
Unit tests for Level 4 - APA Planner

Tests plan generation for surgical, deep, and fast paths.
Tests MCTS integration and solver status determination.
"""

import pytest
from src.core.level4_apa_planner.planner import APAPlanner
from src.core.shared.contracts import (
    IntentPayload, RoutingPayload, CriticalityLevel, RoutePath, OperationType
)


@pytest.fixture
def planner():
    return APAPlanner()


@pytest.fixture
def surgical_routing():
    """Surgical routing for critical operations."""
    intent = IntentPayload(
        op=OperationType.CREATE, target="auth_service.py",
        goal="SECURITY_HARDEN", confidence=0.9, context="",
        raw_code="", language="python"
    )
    return RoutingPayload(
        intent=intent,
        criticality=CriticalityLevel.SURGICAL_CRITICAL,
        route=RoutePath.SURGICAL_PATH,
        reason="Critical node"
    )


@pytest.fixture
def deep_routing():
    """Deep routing for moderate operations."""
    intent = IntentPayload(
        op=OperationType.CREATE, target="feature_module.py",
        goal="FEATURE_ADD", confidence=0.8, context="",
        raw_code="", language="python"
    )
    return RoutingPayload(
        intent=intent,
        criticality=CriticalityLevel.DEEP_MODERATE,
        route=RoutePath.DEEP_PATH,
        reason="Moderate operation"
    )


@pytest.fixture
def fast_routing():
    """Fast routing for simple operations."""
    intent = IntentPayload(
        op=OperationType.EXPLAIN, target="utils.py",
        goal="READABILITY", confidence=0.7, context="",
        raw_code="", language="python"
    )
    return RoutingPayload(
        intent=intent,
        criticality=CriticalityLevel.FAST_STANDARD,
        route=RoutePath.FAST_PATH,
        reason="Simple operation"
    )


class TestAPAPlanner:
    """Tests for the APAPlanner class."""

    def test_generate_plan_returns_execution_plan(self, planner, surgical_routing):
        """Should return a valid ExecutionPlan."""
        plan = planner.generate_plan(surgical_routing)
        assert plan.plan_id is not None
        assert len(plan.plan_id) > 0
        assert isinstance(plan.steps, list)
        assert len(plan.steps) > 0

    def test_surgical_path_has_multiple_steps(self, planner, surgical_routing):
        """Surgical path should generate multiple steps."""
        plan = planner.generate_plan(surgical_routing)
        assert len(plan.steps) >= 3  # Analyze + Scrape + Generate + Validate

    def test_surgical_path_includes_symbolic_validation(self, planner, surgical_routing):
        """Surgical path should always include symbolic validation."""
        plan = planner.generate_plan(surgical_routing)
        actions = [s.action for s in plan.steps]
        assert "SYMBOLIC_VALIDATION" in actions

    def test_surgical_create_includes_scrape(self, planner):
        """Surgical CREATE should include SCRAPE_PATTERNS step."""
        intent = IntentPayload(
            op=OperationType.CREATE, target="auth.py",
            goal="FEATURE_ADD", confidence=0.9, context="",
            raw_code="", language="python", scrap_query="modern auth"
        )
        routing = RoutingPayload(
            intent=intent,
            criticality=CriticalityLevel.SURGICAL_CRITICAL,
            route=RoutePath.SURGICAL_PATH, reason=""
        )
        plan = planner.generate_plan(routing)
        actions = [s.action for s in plan.steps]
        assert "SCRAPE_PATTERNS" in actions
        assert "GENERATE_CODE" in actions

    def test_surgical_debug_includes_trace(self, planner):
        """Surgical DEBUG should include TRACE_EXECUTION."""
        intent = IntentPayload(
            op=OperationType.DEBUG, target="auth.py",
            goal="BUG_FIX", confidence=0.9, context="",
            raw_code="", language="python"
        )
        routing = RoutingPayload(
            intent=intent,
            criticality=CriticalityLevel.SURGICAL_CRITICAL,
            route=RoutePath.SURGICAL_PATH, reason=""
        )
        plan = planner.generate_plan(routing)
        actions = [s.action for s in plan.steps]
        assert "TRACE_EXECUTION" in actions
        assert "PATCH_FIX" in actions

    def test_surgical_delete_includes_dependencies_check(self, planner):
        """Surgical DELETE should include CHECK_DEPENDENCIES."""
        intent = IntentPayload(
            op=OperationType.DELETE, target="auth.py",
            goal="BUG_FIX", confidence=0.9, context="",
            raw_code="", language="python"
        )
        routing = RoutingPayload(
            intent=intent,
            criticality=CriticalityLevel.SURGICAL_CRITICAL,
            route=RoutePath.SURGICAL_PATH, reason=""
        )
        plan = planner.generate_plan(routing)
        actions = [s.action for s in plan.steps]
        assert "CHECK_DEPENDENCIES" in actions
        assert "DELETE_AST_NODE" in actions

    def test_deep_path_includes_structure_analysis(self, planner, deep_routing):
        """Deep path should include ANALYZE_STRUCTURE."""
        plan = planner.generate_plan(deep_routing)
        actions = [s.action for s in plan.steps]
        assert "ANALYZE_STRUCTURE" in actions

    def test_deep_path_includes_syntax_validation(self, planner, deep_routing):
        """Deep path should include SYNTAX_VALIDATION."""
        plan = planner.generate_plan(deep_routing)
        actions = [s.action for s in plan.steps]
        assert "SYNTAX_VALIDATION" in actions

    def test_fast_path_has_minimal_steps(self, planner, fast_routing):
        """Fast path should have minimal steps."""
        plan = planner.generate_plan(fast_routing)
        assert len(plan.steps) <= 3

    def test_fast_explain_includes_explain_step(self, planner):
        """Fast EXPLAIN should include EXPLAIN_CODE step."""
        intent = IntentPayload(
            op=OperationType.EXPLAIN, target="utils.py",
            goal="READABILITY", confidence=0.7, context="",
            raw_code="", language="python"
        )
        routing = RoutingPayload(
            intent=intent,
            criticality=CriticalityLevel.FAST_STANDARD,
            route=RoutePath.FAST_PATH, reason=""
        )
        plan = planner.generate_plan(routing)
        actions = [s.action for s in plan.steps]
        assert "EXPLAIN_CODE" in actions

    def test_plan_steps_have_ids(self, planner, surgical_routing):
        """Each step should have a step_id."""
        plan = planner.generate_plan(surgical_routing)
        for step in plan.steps:
            assert hasattr(step, 'step_id')

    def test_plan_steps_have_actions(self, planner, surgical_routing):
        """Each step should have an action."""
        plan = planner.generate_plan(surgical_routing)
        for step in plan.steps:
            assert step.action is not None
            assert len(step.action) > 0

    def test_mcts_simulations_tracked(self, planner, surgical_routing):
        """Plan should track MCTS simulation count."""
        plan = planner.generate_plan(surgical_routing)
        assert plan.mcts_simulations >= 0

    def test_solver_status_fast_path(self, planner, fast_routing):
        """Fast path should have SKIPPED_FAST_PATH solver status."""
        plan = planner.generate_plan(fast_routing)
        assert plan.solver_status == "SKIPPED_FAST_PATH"

    def test_solver_status_surgical_or_deep(self, planner, surgical_routing):
        """Surgical path should run the solver and set a status."""
        plan = planner.generate_plan(surgical_routing)
        # Could be PROVEN, TIMEOUT_SUBDIVIDE_REQUIRED, HEURISTIC_FALLBACK, etc.
        assert plan.solver_status is not None
        assert len(plan.solver_status) > 0

    def test_step_target_node_name_set(self, planner, surgical_routing):
        """Steps should have target_node_name set to the intent target."""
        plan = planner.generate_plan(surgical_routing)
        for step in plan.steps:
            assert step.target_node_name == surgical_routing.intent.target

    def test_surgical_refactor_includes_replace(self, planner):
        """Surgical REFACTOR/OPTIMIZE should include REPLACE_AST_NODE."""
        intent = IntentPayload(
            op=OperationType.REFACTOR, target="auth.py",
            goal="SECURITY_HARDEN", confidence=0.9, context="",
            raw_code="", language="python"
        )
        routing = RoutingPayload(
            intent=intent,
            criticality=CriticalityLevel.SURGICAL_CRITICAL,
            route=RoutePath.SURGICAL_PATH, reason=""
        )
        plan = planner.generate_plan(routing)
        actions = [s.action for s in plan.steps]
        assert "REPLACE_AST_NODE" in actions
