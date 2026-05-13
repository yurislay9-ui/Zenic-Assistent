"""
Tests for Z3Solver constructor, properties, type lattice, and annotation parsing.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.z3_solver import Z3Solver, HAS_Z3


# ============================================================
#  Constructor and Property Tests
# ============================================================

class TestZ3SolverConstructor:
    """Tests for Z3Solver initialization and properties."""

    def test_default_timeout(self):
        """Should initialize with default timeout of 15000ms."""
        s = Z3Solver()
        assert s.timeout_ms == 15000

    def test_custom_timeout(self):
        """Should accept custom timeout_ms parameter."""
        s = Z3Solver(timeout_ms=10000)
        assert s.timeout_ms == 10000

    def test_solver_type_property(self):
        """solver_type should be 'Z3' or 'AC3_FALLBACK' depending on availability."""
        s = Z3Solver()
        assert s.solver_type in ("Z3", "AC3_FALLBACK")

    def test_solver_type_matches_has_z3(self):
        """solver_type should be 'Z3' when HAS_Z3 is True, else 'AC3_FALLBACK'."""
        s = Z3Solver()
        if HAS_Z3:
            assert s.solver_type == "Z3"
        else:
            assert s.solver_type == "AC3_FALLBACK"

    def test_internal_state_initialized(self):
        """Should initialize internal encoding maps and sort counter."""
        s = Z3Solver()
        assert s._encode_map == {}
        assert s._decode_map == {}
        assert s._next_encode_id == 0
        assert s._sort_counter == 0


# ============================================================
#  Type Lattice Tests
# ============================================================

class TestTypeLattice:
    """Tests for the _TYPE_LATTICE class attribute."""

    def test_type_lattice_exists(self):
        """Z3Solver should have _TYPE_LATTICE attribute."""
        assert hasattr(Z3Solver, "_TYPE_LATTICE")

    def test_type_lattice_compatibility(self):
        """int should be compatible with float and object."""
        lattice = Z3Solver._TYPE_LATTICE
        assert "float" in lattice["int"]
        assert "object" in lattice["int"]

    def test_type_lattice_none(self):
        """None type should be compatible with object and unknown."""
        lattice = Z3Solver._TYPE_LATTICE
        assert "object" in lattice["None"]
        assert "unknown" in lattice["None"]

    def test_type_lattice_bool_compatibility(self):
        """bool should be compatible with int (Python semantics)."""
        lattice = Z3Solver._TYPE_LATTICE
        assert "int" in lattice["bool"]

    def test_type_lattice_unknown_is_minimal(self):
        """unknown should only be compatible with itself."""
        lattice = Z3Solver._TYPE_LATTICE
        assert lattice["unknown"] == {"unknown"}


# ============================================================
#  Annotation-to-Types Tests
# ============================================================

class TestAnnotationToTypes:
    """Tests for _annotation_to_types helper method."""

    def test_simple_int(self, solver):
        """Should parse 'int' annotation."""
        types = solver._annotation_to_types("int")
        assert "int" in types

    def test_optional_type(self, solver):
        """Should parse 'Optional[int]' annotation."""
        types = solver._annotation_to_types("Optional[int]")
        assert isinstance(types, list)
        assert len(types) > 0

    def test_none_annotation(self, solver):
        """Should handle None annotation."""
        types = solver._annotation_to_types(None)
        assert isinstance(types, list)

    def test_empty_annotation(self, solver):
        """Should handle empty string annotation."""
        types = solver._annotation_to_types("")
        assert isinstance(types, list)

    def test_union_type(self, solver):
        """Should parse 'Union[int, str]' annotation."""
        types = solver._annotation_to_types("Union[int, str]")
        assert isinstance(types, list)
        assert len(types) >= 2
