"""Tests for SymbolicValue and SymbolicPath classes."""

from src.core.shared.symbolic_executor import (
    SymbolicValue,
    SymbolicPath,
)


# ============================================================
#  SymbolicValue Tests
# ============================================================

class TestSymbolicValue:
    """Tests for SymbolicValue class."""

    def test_default_initialization(self):
        """Should initialize with default values."""
        sv = SymbolicValue("x")
        assert sv.name == "x"
        assert sv.var_type == "any"
        assert sv.constraint is None
        assert sv.concrete is None

    def test_custom_initialization(self):
        """Should accept custom type, constraint, and concrete value."""
        constraint = lambda v: v > 0
        sv = SymbolicValue("y", var_type="int", constraint=constraint, concrete=42)
        assert sv.name == "y"
        assert sv.var_type == "int"
        assert sv.constraint is constraint
        assert sv.concrete == 42

    def test_repr_with_concrete(self):
        """Should show concrete value in repr."""
        sv = SymbolicValue("z", var_type="int", concrete=10)
        r = repr(sv)
        assert "z" in r
        assert "10" in r

    def test_repr_without_concrete(self):
        """Should show symbolic representation when no concrete value."""
        sv = SymbolicValue("a", var_type="str")
        r = repr(sv)
        assert "a" in r
        assert "str" in r

    def test_var_type_bool(self):
        """Should support bool type."""
        sv = SymbolicValue("flag", var_type="bool", concrete=True)
        assert sv.var_type == "bool"
        assert sv.concrete is True

    def test_var_type_none(self):
        """Should handle None concrete value properly."""
        sv = SymbolicValue("x", var_type="int", concrete=None)
        assert sv.concrete is None
        # repr should not show concrete since it's None
        r = repr(sv)
        assert not ("=" in r and "None" in r), f"Repr should not show concrete value when it is None: {r}"


# ============================================================
#  SymbolicPath Tests
# ============================================================

class TestSymbolicPath:
    """Tests for SymbolicPath class."""

    def test_default_initialization(self):
        """Should initialize with default empty values."""
        sp = SymbolicPath()
        assert sp.condition == []
        assert sp.result is None
        assert sp.is_pruned is False
        assert sp.variables == {}
        assert sp.z3_conditions == []
        assert sp.assignments == []
        assert sp.return_values == []

    def test_custom_initialization(self):
        """Should accept custom values."""
        sp = SymbolicPath(
            condition=["x > 0"],
            result="some_result",
            is_pruned=True,
            variables={"x": SymbolicValue("x", "int")},
        )
        assert sp.condition == ["x > 0"]
        assert sp.result == "some_result"
        assert sp.is_pruned is True
        assert "x" in sp.variables

    def test_add_condition_string_only(self):
        """Should add string condition without Z3 constraint."""
        sp = SymbolicPath()
        sp.add_condition("x > 0")
        assert "x > 0" in sp.condition
        assert len(sp.z3_conditions) == 0

    def test_add_condition_with_z3(self):
        """Should add both string and Z3 condition."""
        sp = SymbolicPath()
        sp.add_condition("x > 0", z3_cond="mock_z3_condition")
        assert "x > 0" in sp.condition
        assert "mock_z3_condition" in sp.z3_conditions

    def test_add_assignment(self):
        """Should record variable assignments."""
        sp = SymbolicPath()
        sp.add_assignment("x", "42")
        sp.add_assignment("y", "x + 1")
        assert len(sp.assignments) == 2
        assert sp.assignments[0] == ("x", "42")
        assert sp.assignments[1] == ("y", "x + 1")

    def test_add_return(self):
        """Should record return values with type."""
        sp = SymbolicPath()
        sp.add_return("42", "int")
        sp.add_return("None", "None")
        assert len(sp.return_values) == 2
        assert sp.return_values[0]["desc"] == "42"
        assert sp.return_values[0]["type"] == "int"
        assert sp.return_values[1]["desc"] == "None"

    def test_add_return_default_type(self):
        """add_return should default to 'any' type."""
        sp = SymbolicPath()
        sp.add_return("some_value")
        assert sp.return_values[0]["type"] == "any"

    def test_is_feasible_no_conditions(self):
        """Path with no conditions should be feasible."""
        sp = SymbolicPath()
        assert sp.is_feasible() is True

    def test_is_feasible_consistent_conditions(self):
        """Path with consistent conditions should be feasible."""
        sp = SymbolicPath()
        sp.add_condition("x > 0")
        sp.add_condition("y > 0")
        assert sp.is_feasible() is True

    def test_is_feasible_contradictory_conditions(self):
        """Path with contradictory string conditions should be infeasible."""
        sp = SymbolicPath()
        sp.add_condition("x > 0")
        sp.add_condition("NOT_x > 0")
        assert sp.is_feasible() is False

    def test_max_z3_conditions(self):
        """Should not exceed MAX_Z3_CONDITIONS."""
        assert SymbolicPath.MAX_Z3_CONDITIONS == 50
        sp = SymbolicPath()
        for i in range(60):
            sp.add_condition(f"cond_{i}", z3_cond=f"z3_cond_{i}")
        assert len(sp.z3_conditions) <= SymbolicPath.MAX_Z3_CONDITIONS
