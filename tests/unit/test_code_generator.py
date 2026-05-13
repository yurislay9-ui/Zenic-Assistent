"""
Unit tests for Code Generator

Tests contextual code generation for different operations and languages.
"""

import pytest
from src.core.code_generator import CodeGenerator
from src.core.shared.contracts import (
    IntentPayload, ExecutionPlan, PlanStep, OperationType, GoalType
)


@pytest.fixture
def code_gen():
    """Create a CodeGenerator instance. Requires an orchestrator mock."""
    class MockOrchestrator:
        pass
    return CodeGenerator(MockOrchestrator())


@pytest.fixture
def create_intent():
    return IntentPayload(
        op=OperationType.CREATE, target="auth_service.py",
        goal=GoalType.FEATURE_ADD, confidence=0.9, context="",
        raw_code="", language="python"
    )


@pytest.fixture
def sample_plan():
    return ExecutionPlan(
        plan_id="test-plan",
        steps=[
            PlanStep(step_id=1, action="ANALYZE_STRUCTURE"),
            PlanStep(step_id=2, action="GENERATE_CODE"),
        ],
        solver_status="HEURISTIC_FALLBACK",
        mcts_simulations=10,
        mcts_depth_reached=2
    )


class TestCodeGenerator:
    """Tests for the CodeGenerator class."""

    def test_generate_contextual_code_python(self, code_gen, create_intent, sample_plan):
        """Should generate Python code for a CREATE intent."""
        ast_analysis = {"functions": 0, "classes": 0, "max_complexity": 0,
                        "function_names": [], "class_names": []}
        result = code_gen.generate_contextual_code(create_intent, ast_analysis, sample_plan, "python")
        assert result is not None
        assert len(result) > 0
        assert "def " in result or "class " in result

    def test_generate_contextual_code_returns_string(self, code_gen, create_intent, sample_plan):
        """Should always return a string."""
        ast_analysis = {"functions": 0, "classes": 0, "max_complexity": 0,
                        "function_names": [], "class_names": []}
        result = code_gen.generate_contextual_code(create_intent, ast_analysis, sample_plan, "python")
        assert isinstance(result, str)

    def test_generate_pipeline_driven_code(self, code_gen, create_intent):
        """Should generate code based on pipeline data."""
        ast_analysis = {"functions": 1, "classes": 0, "max_complexity": 3,
                        "function_names": ["existing_func"], "class_names": []}
        plan = ExecutionPlan(
            plan_id="test",
            steps=[PlanStep(step_id=1, action="REPLACE_AST_NODE")],
            solver_status="PROVEN",
            mcts_simulations=5,
            mcts_depth_reached=2
        )
        result = code_gen.generate_pipeline_driven_code(create_intent, ast_analysis, plan, "python")
        assert isinstance(result, str)

    def test_extract_solver_insights_none(self, code_gen):
        """Should handle None solver proof."""
        insights = code_gen.extract_solver_insights(None)
        # Returns a dict with default values when no proof available
        assert isinstance(insights, (dict, list, type(None)))

    def test_extract_solver_insights_dict(self, code_gen):
        """Should extract insights from solver proof dict."""
        proof = {"status": "PROVEN", "assignment": {"target_type": "critical"}}
        insights = code_gen.extract_solver_insights(proof)
        assert insights is not None

    def test_extract_ast_context(self, code_gen):
        """Should extract context from AST analysis."""
        ast_analysis = {
            "functions": 3, "classes": 1, "max_complexity": 5,
            "function_names": ["func1", "func2", "func3"],
            "class_names": ["MyClass"],
            "connections": ["method:init", "method:process"]
        }
        context = code_gen.extract_ast_context(ast_analysis)
        assert context is not None
        assert len(context) > 0
