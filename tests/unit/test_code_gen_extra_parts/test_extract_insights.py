"""
Tests for extract_solver_insights, extract_ast_context, extract_symbolic_insights.

Extended tests for CodeGenerator static analysis methods.
"""

import pytest

from src.core.code_generator import CodeGenerator


class TestExtractSolverInsights:
    """Extended tests for extract_solver_insights static method."""

    def test_none_proof(self):
        """Should return default insights for None proof."""
        insights = CodeGenerator.extract_solver_insights(None)
        assert insights["null_safety_required"] is False
        assert insights["type_safety_required"] is False
        assert insights["critical_target"] is False
        assert insights["status"] == "none"

    def test_empty_dict_proof(self):
        """Should handle empty dict proof (treated as falsy)."""
        insights = CodeGenerator.extract_solver_insights({})
        assert insights["status"] == "none"
        assert isinstance(insights["validated_constraints"], list)

    def test_proven_status(self):
        """Should extract validated constraints from PROVEN proof."""
        proof = {
            "status": "PROVEN",
            "proof": "Z3 EnumSort proved null-safety constraints",
            "solver_type": "Z3_ENUMSORT",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "PROVEN"
        assert insights["null_safety_required"] is True
        assert len(insights["validated_constraints"]) > 0

    def test_proven_type_safety(self):
        """Should detect type safety requirement from PROVEN proof."""
        proof = {
            "status": "PROVEN",
            "proof": "Type assignment verified",
            "solver_type": "Z3",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["type_safety_required"] is True

    def test_proven_critical_target(self):
        """Should detect critical target from PROVEN proof."""
        proof = {
            "status": "PROVEN",
            "proof": "Critical constraint verified",
            "solver_type": "Z3",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["critical_target"] is True

    def test_violated_status(self):
        """Should extract violated constraints from VIOLATED proof."""
        proof = {
            "status": "VIOLATED",
            "counterexamples": [{"x": "None", "y": 0}],
            "solver_type": "Z3",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "VIOLATED"
        assert len(insights["violated_constraints"]) > 0
        assert insights["null_safety_required"] is True

    def test_likely_violated_status(self):
        """Should handle LIKELY_VIOLATED status."""
        proof = {
            "status": "LIKELY_VIOLATED",
            "counterexamples": [{"a": "type_mismatch"}],
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "LIKELY_VIOLATED"
        assert insights["type_safety_required"] is True

    def test_satisfied_status(self):
        """Should extract assignment from SATISFIED proof."""
        proof = {
            "status": "SATISFIED",
            "assignment": {"x": 1, "y": 2},
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "SATISFIED"
        assert len(insights["validated_constraints"]) >= 2

    def test_satisfied_non_dict_assignment(self):
        """Should handle non-dict assignment in SATISFIED proof."""
        proof = {
            "status": "SATISFIED",
            "assignment": None,
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "SATISFIED"

    def test_constraints_in_proof(self):
        """Should detect critical/null from constraints list."""
        proof = {
            "status": "UNKNOWN",
            "constraints": ["critical: must not be null", "null check required"],
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["critical_target"] is True
        assert insights["null_safety_required"] is True

    def test_constraints_as_objects(self):
        """Should handle Constraint objects in constraints list."""
        from src.core.shared.constraint_solver import Constraint

        c = Constraint("x", "y", lambda a, b: a < b, description="critical safety")
        proof = {
            "status": "UNKNOWN",
            "constraints": [c],
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["critical_target"] is True

    def test_solver_type_extracted(self):
        """Should extract solver_type from proof."""
        proof = {"status": "PROVEN", "solver_type": "Z3_ENUMSORT"}
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["solver_type"] == "Z3_ENUMSORT"


class TestExtractASTContext:
    """Extended tests for extract_ast_context static method."""

    def test_none_ast(self):
        """Should return default context for None AST analysis."""
        ctx = CodeGenerator.extract_ast_context(None)
        assert ctx["function_signatures"] == []
        assert ctx["max_complexity"] == 0

    def test_empty_ast(self):
        """Should return default context for empty AST analysis."""
        ctx = CodeGenerator.extract_ast_context({})
        assert ctx["function_names"] == []
        assert ctx["class_names"] == []

    def test_extends_connections(self):
        """Should detect class hierarchy from extends: connections."""
        ast = {
            "function_names": [],
            "class_names": ["ChildClass"],
            "max_complexity": 0,
            "connections": ["extends:BaseClass"],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert len(ctx["class_hierarchies"]) > 0

    def test_method_connections(self):
        """Should detect call relationships from method: connections."""
        ast = {
            "function_names": [],
            "class_names": [],
            "max_complexity": 0,
            "connections": ["MyClassmethod:process"],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert len(ctx["call_relationships"]) > 0

    def test_import_dependencies(self):
        """Should detect import dependencies from other connections."""
        ast = {
            "function_names": [],
            "class_names": [],
            "max_complexity": 0,
            "connections": ["utils.helper"],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "utils.helper" in ctx["import_dependencies"]

    def test_getter_pattern(self):
        """Should detect getter pattern."""
        ast = {
            "function_names": ["get_name", "get_age"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "getter" in ctx["existing_patterns"]

    def test_setter_pattern(self):
        """Should detect setter pattern."""
        ast = {
            "function_names": ["set_name"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "setter" in ctx["existing_patterns"]

    def test_private_methods_pattern(self):
        """Should detect private methods pattern."""
        ast = {
            "function_names": ["_helper", "__init__"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "private_methods" in ctx["existing_patterns"]

    def test_validation_pattern(self):
        """Should detect validation pattern."""
        ast = {
            "function_names": ["validate_input", "check_status"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "validation" in ctx["existing_patterns"]

    def test_max_complexity(self):
        """Should extract max_complexity from AST analysis."""
        ast = {
            "function_names": [],
            "class_names": [],
            "max_complexity": 15,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert ctx["max_complexity"] == 15


class TestExtractSymbolicInsights:
    """Tests for extract_symbolic_insights static method."""

    def test_none_result(self):
        """Should return default insights for None result."""
        insights = CodeGenerator.extract_symbolic_insights(None)
        assert insights["symbolic_violations"] == []
        assert insights["paths_explored"] == 0

    def test_sandbox_result_with_warnings(self):
        """Should extract Z3-proven and heuristic violations from warnings."""
        class MockResult:
            warnings = [
                "Symbolic (Z3 PROVEN): division by zero at line 5",
                "Symbolic: potential null dereference",
                "Regular warning",
            ]
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert len(insights["z3_proven_violations"]) == 1
        assert len(insights["division_by_zero_risks"]) == 1
        assert len(insights["symbolic_violations"]) == 1

    def test_sandbox_result_with_metrics(self):
        """Should extract metrics from sandbox result."""
        class MockResult:
            warnings = []
            metrics = {
                "paths_explored": 25,
                "paths_pruned": 5,
                "feasible_paths": 20,
                "smt_paths_available": True,
                "test_inputs_sample": [{"x": 1, "y": 2}],
            }

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert insights["paths_explored"] == 25
        assert insights["paths_pruned"] == 5
        assert insights["feasible_paths"] == 20
        assert insights["smt_paths_available"] is True
        assert len(insights["concrete_test_inputs"]) == 1

    def test_sandbox_result_none_deref(self):
        """Should detect None dereference risks."""
        class MockResult:
            warnings = ["Symbolic (Z3 PROVEN): none dereference at line 10"]
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert len(insights["null_dereference_risks"]) == 1

    def test_sandbox_result_index_oob(self):
        """Should detect index out of bounds risks."""
        class MockResult:
            warnings = ["Symbolic (Z3 PROVEN): index out of bounds at line 3"]
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert len(insights["index_oob_risks"]) == 1

    def test_empty_metrics(self):
        """Should handle empty metrics dict."""
        class MockResult:
            warnings = []
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert insights["paths_explored"] == 0
