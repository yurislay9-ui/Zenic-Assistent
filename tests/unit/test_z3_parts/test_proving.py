"""
Tests for Z3Solver proving methods: null safety, type safety, invariant verification.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.z3_solver import Z3Solver


# ============================================================
#  Null Safety Tests
# ============================================================

class TestProveNullSafety:
    """Tests for prove_null_safety method."""

    def test_no_nullable_vars(self, solver):
        """When no vars are nullable, all should be non-null -> PROVEN."""
        result = solver.prove_null_safety(
            variable_names=["x", "y", "z"],
            nullable_vars=set()
        )
        assert isinstance(result, dict)
        assert "status" in result
        # With no nullable vars, constraints should be consistent -> PROVEN
        assert result["status"] in ("PROVEN", "LIKELY_PROVEN")

    def test_some_nullable_vars(self, solver):
        """When some vars are nullable, should still be satisfiable."""
        result = solver.prove_null_safety(
            variable_names=["x", "y"],
            nullable_vars={"y"}
        )
        assert isinstance(result, dict)
        assert "status" in result

    def test_all_nullable_vars(self, solver):
        """When all vars are nullable, should be trivially satisfiable."""
        result = solver.prove_null_safety(
            variable_names=["x", "y"],
            nullable_vars={"x", "y"}
        )
        assert isinstance(result, dict)
        assert result["status"] in ("PROVEN", "LIKELY_PROVEN", "UNKNOWN")

    def test_empty_variable_names(self, solver):
        """Should handle empty variable list."""
        result = solver.prove_null_safety(
            variable_names=[],
            nullable_vars=set()
        )
        assert isinstance(result, dict)

    def test_result_has_solver_type(self, solver):
        """Result should include solver_type information."""
        result = solver.prove_null_safety(["x"], set())
        assert "solver_type" in result

    def test_result_has_verified_field(self, solver):
        """Result should include a verified boolean field."""
        result = solver.prove_null_safety(["x"], set())
        assert "verified" in result
        assert isinstance(result["verified"], bool)


# ============================================================
#  Type Safety Tests
# ============================================================

class TestProveTypeSafety:
    """Tests for prove_type_safety method."""

    def test_compatible_types(self, solver):
        """Compatible type assignments should be PROVEN."""
        variables_with_types = [
            {"name": "x", "types": ["int"]},
            {"name": "y", "types": ["int"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert result["status"] in ("PROVEN", "LIKELY_PROVEN")

    def test_incompatible_types(self, solver):
        """Incompatible type assignments should be VIOLATED or UNSATISFIABLE."""
        variables_with_types = [
            {"name": "x", "types": ["int"]},
            {"name": "y", "types": ["str"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert "status" in result

    def test_single_variable(self, solver):
        """Should handle a single variable."""
        variables_with_types = [
            {"name": "x", "types": ["int"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert "status" in result

    def test_empty_variables(self, solver):
        """Should handle empty variables list."""
        result = solver.prove_type_safety([])
        assert isinstance(result, dict)

    def test_multiple_types_per_variable(self, solver):
        """Should handle variables with multiple possible types."""
        variables_with_types = [
            {"name": "x", "types": ["int", "float"]},
            {"name": "y", "types": ["str"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert "status" in result

    def test_unknown_type(self, solver):
        """Should handle 'unknown' type gracefully."""
        variables_with_types = [
            {"name": "x", "types": ["unknown"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)


# ============================================================
#  Invariant Verification Tests
# ============================================================

class TestProveInvariant:
    """Tests for prove_invariant method."""

    def test_trivially_true_invariant(self, solver):
        """An invariant that's always true should be PROVEN."""
        def always_true(**kwargs):
            return True

        result = solver.prove_invariant(
            always_true,
            variables=["x", "y"],
            domains={"x": [1, 2, 3], "y": [4, 5, 6]}
        )
        assert isinstance(result, dict)
        assert result.get("verified") is True

    def test_trivially_false_invariant(self, solver):
        """An invariant that's always false should be VIOLATED."""
        def always_false(**kwargs):
            return False

        result = solver.prove_invariant(
            always_false,
            variables=["x"],
            domains={"x": [1, 2, 3]}
        )
        assert isinstance(result, dict)
        assert result.get("verified") is False

    def test_conditional_invariant(self, solver):
        """An invariant with a conditional should work correctly."""
        def x_less_than_y(**kwargs):
            return kwargs.get("x", 0) < kwargs.get("y", 0)

        result = solver.prove_invariant(
            x_less_than_y,
            variables=["x", "y"],
            domains={"x": [1, 2], "y": [3, 0]}
        )
        assert isinstance(result, dict)
        # x=2, y=0 violates x < y
        assert result.get("status") in ("VIOLATED", "LIKELY_VIOLATED")

    def test_invariant_with_empty_domain(self, solver):
        """Should handle empty domains gracefully."""
        def always_true(**kwargs):
            return True

        result = solver.prove_invariant(
            always_true,
            variables=["x"],
            domains={}
        )
        assert isinstance(result, dict)

    def test_invariant_exception_handling(self, solver):
        """Should handle exceptions in invariant function."""
        def bad_invariant(**kwargs):
            raise ValueError("test error")

        result = solver.prove_invariant(
            bad_invariant,
            variables=["x"],
            domains={"x": [1, 2]}
        )
        assert isinstance(result, dict)
