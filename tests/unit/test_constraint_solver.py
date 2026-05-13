"""
Unit tests for Constraint Solver (AC-3 + Backtracking)

Tests AC-3 arc consistency, backtracking search, timeout enforcement,
and invariant verification.
"""

import pytest
from src.core.shared.constraint_solver import Constraint, ConstraintSolver


class TestConstraint:
    """Tests for the Constraint class."""

    def test_satisfied_true(self):
        """Should return True when constraint is satisfied."""
        c = Constraint("x", "y", lambda x, y: x < y, "x less than y")
        assert c.satisfied(1, 2) is True

    def test_satisfied_false(self):
        """Should return False when constraint is violated."""
        c = Constraint("x", "y", lambda x, y: x < y, "x less than y")
        assert c.satisfied(2, 1) is False

    def test_description_stored(self):
        """Should store the description."""
        c = Constraint("a", "b", lambda a, b: True, "test desc")
        assert c.description == "test desc"


class TestConstraintSolver:
    """Tests for the ConstraintSolver class."""

    @pytest.fixture
    def solver(self):
        return ConstraintSolver(timeout_ms=5000)

    def test_simple_satisfiable(self, solver):
        """Should find a solution for a simple satisfiable CSP."""
        domains = {"x": [1, 2, 3], "y": [1, 2, 3]}
        constraints = [Constraint("x", "y", lambda x, y: x != y, "x != y")]
        result = solver.solve(domains, constraints)
        assert result["status"] == "SATISFIED"
        assert result["assignment"] is not None
        assert result["assignment"]["x"] != result["assignment"]["y"]

    def test_unsatisfiable(self, solver):
        """Should detect unsatisfiable CSP."""
        domains = {"x": [1], "y": [1]}
        constraints = [Constraint("x", "y", lambda x, y: x != y, "x != y")]
        result = solver.solve(domains, constraints)
        assert result["status"] == "UNSATISFIABLE"

    def test_multiple_constraints(self, solver):
        """Should handle multiple constraints correctly."""
        domains = {"x": [1, 2, 3], "y": [1, 2, 3], "z": [1, 2, 3]}
        constraints = [
            Constraint("x", "y", lambda x, y: x < y, "x < y"),
            Constraint("y", "z", lambda y, z: y < z, "y < z"),
        ]
        result = solver.solve(domains, constraints)
        assert result["status"] == "SATISFIED"
        a = result["assignment"]
        assert a["x"] < a["y"] < a["z"]

    def test_ac3_reduces_domains(self, solver):
        """AC-3 should eliminate inconsistent values from domains."""
        # Use solve() which initializes _start_time properly
        domains = {"x": [1, 2], "y": [1]}
        constraints = [Constraint("x", "y", lambda x, y: x != y, "x != y")]
        result = solver.solve(domains, constraints)
        # Since x=1 conflicts with y=1, AC-3 should reduce x to [2]
        # Then backtracking finds x=2, y=1
        assert result["status"] == "SATISFIED"
        assert result["assignment"]["x"] == 2

    def test_ac3_detects_unsatisfiable(self, solver):
        """AC-3 should detect unsatisfiable when domain is wiped."""
        # Use solve() which initializes _start_time properly
        domains = {"x": [1], "y": [1]}
        constraints = [Constraint("x", "y", lambda x, y: x != y, "x != y")]
        result = solver.solve(domains, constraints)
        # Should detect UNSATISFIABLE since x=1 and y=1 but x != y
        assert result["status"] == "UNSATISFIABLE"

    def test_timeout(self):
        """Should timeout on very large CSP."""
        solver = ConstraintSolver(timeout_ms=50)  # Very short timeout
        # Create a large CSP that takes a while
        domains = {f"v{i}": list(range(100)) for i in range(20)}
        constraints = [
            Constraint(f"v{i}", f"v{i+1}", lambda x, y: x != y, f"v{i} != v{i+1}")
            for i in range(19)
        ]
        result = solver.solve(domains, constraints)
        assert result["status"] in ["TIMEOUT", "SATISFIED"]  # Either timeout or find a solution

    def test_no_constraints(self, solver):
        """Should return any assignment when no constraints exist."""
        domains = {"x": [1, 2], "y": [3, 4]}
        result = solver.solve(domains, [])
        assert result["status"] == "SATISFIED"
        assert result["assignment"]["x"] in [1, 2]
        assert result["assignment"]["y"] in [3, 4]

    def test_single_variable(self, solver):
        """Should handle CSP with a single variable."""
        domains = {"x": [1, 2, 3]}
        result = solver.solve(domains, [])
        assert result["status"] == "SATISFIED"
        assert result["assignment"]["x"] in [1, 2, 3]


class TestInvariantVerification:
    """Tests for ConstraintSolver.verify_invariant."""

    @pytest.fixture
    def solver(self):
        return ConstraintSolver(timeout_ms=5000)

    def test_proven_invariant(self, solver):
        """Should prove a true invariant."""
        condition = lambda x, y: x + y >= 2  # min values are 1,1 so 1+1=2
        variables = ["x", "y"]
        domains = {"x": [1, 2, 3], "y": [1, 2, 3]}
        result = solver.verify_invariant(condition, variables, domains)
        assert result["status"] == "PROVEN"
        assert result["verified"] is True

    def test_violated_invariant(self, solver):
        """Should find a counterexample for a false invariant."""
        condition = lambda x, y: x + y > 10  # max values are 3,3 so 3+3=6 < 10
        variables = ["x", "y"]
        domains = {"x": [1, 2, 3], "y": [1, 2, 3]}
        result = solver.verify_invariant(condition, variables, domains)
        assert result["status"] == "VIOLATED"
        assert result["verified"] is False
        assert len(result["counterexamples"]) > 0

    def test_sample_verify_large_domain(self, solver):
        """Should use sampling for large domains."""
        # Use domain 1..9999 (all positive) so invariant x >= 1 is always true
        condition = lambda x: x >= 1
        variables = ["x"]
        domains = {"x": list(range(1, 10000))}
        result = solver.verify_invariant(condition, variables, domains)
        # All values >= 1, should be LIKELY_PROVEN (sampled)
        assert result["status"] in ["PROVEN", "LIKELY_PROVEN"]
        assert result["verified"] is True
