"""
Tests for Z3Solver constraint solving and code safety proof methods.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.z3_solver import Z3Solver
from src.core.shared.constraint_solver import Constraint


# ============================================================
#  Constraint Solving Tests
# ============================================================

class TestSolveConstraints:
    """Tests for solve_constraints method."""

    def test_satisfiable_constraints(self, solver):
        """Should find a solution for satisfiable constraints."""
        domains = {"x": [1, 2, 3], "y": [2, 3, 4]}
        constraints = [
            Constraint("x", "y", lambda a, b: a < b, "x < y")
        ]
        result = solver.solve_constraints(domains, constraints)
        assert isinstance(result, dict)
        assert result["status"] in ("SATISFIED",)

    def test_unsatisfiable_constraints(self, solver):
        """Should return UNSATISFIABLE for contradictory constraints."""
        domains = {"x": [1], "y": [1]}
        constraints = [
            Constraint("x", "y", lambda a, b: a < b, "x < y"),
            Constraint("x", "y", lambda a, b: a > b, "x > y"),
        ]
        result = solver.solve_constraints(domains, constraints)
        assert result["status"] == "UNSATISFIABLE"

    def test_no_constraints(self, solver):
        """Should find any solution when no constraints exist."""
        domains = {"x": [1, 2], "y": [3, 4]}
        result = solver.solve_constraints(domains, [])
        assert result["status"] == "SATISFIED"

    def test_empty_domains(self, solver):
        """Should handle empty domains."""
        domains = {}
        result = solver.solve_constraints(domains, [])
        assert isinstance(result, dict)

    def test_assignment_present_on_satisfied(self, solver):
        """SATISFIED result should include an assignment dict."""
        domains = {"x": [1, 2, 3], "y": [4, 5, 6]}
        constraints = [
            Constraint("x", "y", lambda a, b: a < b, "x < y")
        ]
        result = solver.solve_constraints(domains, constraints)
        if result["status"] == "SATISFIED":
            assert result["assignment"] is not None
            assert "x" in result["assignment"]
            assert "y" in result["assignment"]


# ============================================================
#  Code Safety Proof Tests
# ============================================================

class TestProveCodeSafety:
    """Tests for prove_code_safety method."""

    def test_basic_code_safety(self, solver):
        """Should analyze basic code with variables."""
        ast_analysis = {
            "variables": [
                {"name": "x", "annotation": "int", "nullable": False},
                {"name": "y", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "x = 1\ny = 2\n")
        assert isinstance(result, dict)
        assert "overall_status" in result
        assert result["overall_status"] in ("PROVEN", "PARTIAL", "VIOLATED", "UNKNOWN", "ERROR", "LIKELY_PROVEN")

    def test_code_safety_with_nullable(self, solver):
        """Should detect nullable variables and check null safety."""
        ast_analysis = {
            "variables": [
                {"name": "x", "annotation": "Optional[int]", "nullable": True},
                {"name": "y", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "x: Optional[int] = None\ny: int = 1\n")
        assert isinstance(result, dict)
        assert "null_safety" in result

    def test_code_safety_empty_analysis(self, solver):
        """Should handle empty AST analysis."""
        ast_analysis = {
            "variables": [],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "")
        assert isinstance(result, dict)
        assert "overall_status" in result

    def test_code_safety_with_operations(self, solver):
        """Should analyze code with type operations."""
        ast_analysis = {
            "variables": [
                {"name": "a", "annotation": "int", "nullable": False},
                {"name": "b", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [
                {"op": "add", "left_var": "a", "right_var": "b",
                 "left_type": "int", "right_type": "int"},
            ],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "a + b\n")
        assert isinstance(result, dict)
        assert "type_safety" in result

    def test_code_safety_with_invariants(self, solver):
        """Should verify invariants from AST analysis."""
        ast_analysis = {
            "variables": [
                {"name": "idx", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [],
            "invariants": [
                {"kind": "index_bounds", "expr": "idx >= 0", "variables": ["idx"]},
            ],
        }
        result = solver.prove_code_safety(ast_analysis, "items[idx]\n")
        assert isinstance(result, dict)
        assert "invariant_safety" in result

    def test_code_safety_syntax_error_code(self, solver):
        """Should handle code with syntax errors gracefully."""
        ast_analysis = {
            "variables": [],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "def foo( $$$ ")
        assert isinstance(result, dict)
        # Should not crash

    def test_code_safety_result_fields(self, solver):
        """Result should have all expected fields."""
        ast_analysis = {
            "variables": [{"name": "x", "annotation": "int", "nullable": False}],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "x = 1\n")
        assert "null_safety" in result
        assert "type_safety" in result
        assert "invariant_safety" in result
        assert "overall_status" in result
        assert "solver_type" in result
        assert "errors" in result
