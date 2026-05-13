"""
Tests for contextual code generation, generate_intelligent_code, and edge cases.
"""

import pytest

from src.core.code_generator import CodeGenerator
from src.core.shared.contracts import (
    IntentPayload, ExecutionPlan, PlanStep, OperationType, GoalType
)


class TestContextualCodeGeneration:
    """Tests for generate_contextual_code and generate_intelligent_code."""

    def test_generate_contextual_code_no_plan(self, code_gen, create_intent):
        """Should use fallback generation when no plan available."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        result = code_gen.generate_contextual_code(create_intent, ast, None, "python")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_contextual_code_kotlin(self, code_gen, create_intent):
        """Should generate Kotlin code when language is kotlin."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_contextual_code(create_intent, ast, plan, "kotlin")
        assert isinstance(result, str)
        assert "package" in result

    def test_generate_contextual_code_go(self, code_gen, create_intent):
        """Should generate Go code when language is go."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_contextual_code(create_intent, ast, plan, "go")
        assert isinstance(result, str)
        assert "package" in result

    def test_generate_contextual_code_javascript(self, code_gen, create_intent):
        """Should generate JavaScript code when language is javascript."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_contextual_code(create_intent, ast, plan, "javascript")
        assert isinstance(result, str)
        assert "class" in result.lower()

    def test_generate_intelligent_code(self, code_gen, create_intent):
        """Should delegate to generate_contextual_code."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        result = code_gen.generate_intelligent_code(create_intent, ast, "python")
        assert isinstance(result, str)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_special_chars_in_target(self, code_gen, create_intent):
        """Should sanitize special characters in target name."""
        create_intent.target = "my-module@v2.py"
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_pipeline_driven_code(create_intent, ast, plan, "python")
        assert isinstance(result, str)

    def test_unknown_target(self, code_gen):
        """Should handle 'unknown' target gracefully."""
        intent = IntentPayload(
            op=OperationType.CREATE, target="unknown",
            goal=GoalType.FEATURE_ADD, confidence=0.5, context="",
            raw_code="", language="python"
        )
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_pipeline_driven_code(intent, ast, plan, "python")
        assert isinstance(result, str)

    def test_empty_ast_analysis_no_plan(self, code_gen, create_intent):
        """Should handle empty AST analysis without a plan."""
        result = code_gen.generate_contextual_code(create_intent, {}, None, "python")
        assert isinstance(result, str)

    def test_extract_solver_insights_counterexamples_as_string(self):
        """Should handle counterexamples as string (not list)."""
        proof = {
            "status": "VIOLATED",
            "counterexamples": "single counterexample string",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert isinstance(insights["violated_constraints"], list)

    def test_extract_ast_context_complex_connections(self):
        """Should handle complex connection strings."""
        ast = {
            "function_names": ["get_data", "_internal"],
            "class_names": ["DataClass"],
            "max_complexity": 5,
            "connections": [
                "extends:BaseClass",
                "DataClassmethod:process",
                "external.module",
            ],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert len(ctx["class_hierarchies"]) > 0
        assert len(ctx["call_relationships"]) > 0
        assert len(ctx["import_dependencies"]) > 0
        assert "getter" in ctx["existing_patterns"]
        assert "private_methods" in ctx["existing_patterns"]

    def test_generate_feature_module_with_needed_imports(self):
        """Should include import comments for detected dependencies."""
        code = CodeGenerator.generate_feature_module(
            "imported",
            existing_functions=[],
            existing_classes=[],
            needed_imports={"my_module", "helpers"},
        )
        assert "my_module" in code
        assert "helpers" in code

    def test_pipeline_module_proven_header(self, code_gen):
        """Should include Z3 verified header for PROVEN status."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["status"] = "PROVEN"
        solver_insights["validated_constraints"] = ["constraint_1", "constraint_2"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="proven_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "Z3 Verified" in code
