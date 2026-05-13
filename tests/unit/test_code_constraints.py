"""
Unit tests for CodeConstraintBuilder

Tests constraint building for null-safety, type-safety, and domain generation
from AST analysis.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.core.shared.code_constraints import CodeConstraintBuilder
from src.core.shared.constraint_solver import Constraint


class TestBuildNullSafetyConstraints:
    """Tests for CodeConstraintBuilder.build_null_safety_constraints."""

    def test_generates_constraints_for_non_nullable_vars(self):
        """Should generate constraints between non-nullable and nullable variables."""
        variables = [
            {"name": "user_id", "can_be_none": False},
            {"name": "email", "can_be_none": True},
        ]
        constraints = CodeConstraintBuilder.build_null_safety_constraints(variables)
        # One constraint: non-nullable user_id vs nullable email
        assert len(constraints) == 1
        assert isinstance(constraints[0], Constraint)
        assert constraints[0].var1 == "user_id"
        assert constraints[0].var2 == "email"
        assert "null-safety" in constraints[0].description

    def test_no_constraints_when_all_nullable(self):
        """Should produce no constraints when all variables are nullable."""
        variables = [
            {"name": "x", "can_be_none": True},
            {"name": "y", "can_be_none": True},
        ]
        constraints = CodeConstraintBuilder.build_null_safety_constraints(variables)
        assert len(constraints) == 0

    def test_no_constraints_when_all_non_nullable(self):
        """Should produce no constraints when there are no nullable variables."""
        variables = [
            {"name": "a", "can_be_none": False},
            {"name": "b", "can_be_none": False},
        ]
        constraints = CodeConstraintBuilder.build_null_safety_constraints(variables)
        assert len(constraints) == 0

    def test_constraint_predicate_satisfied(self):
        """The null-safety constraint should be satisfied when nullable is not None."""
        variables = [
            {"name": "id", "can_be_none": False},
            {"name": "val", "can_be_none": True},
        ]
        constraints = CodeConstraintBuilder.build_null_safety_constraints(variables)
        c = constraints[0]
        # If val is not None, constraint is satisfied regardless of id
        assert c.satisfied("some_value", "not_none") is True
        # If val is None but id is not None, constraint is satisfied
        assert c.satisfied("not_none", None) is True

    def test_constraint_predicate_violated(self):
        """The null-safety constraint should be violated when both are None."""
        variables = [
            {"name": "id", "can_be_none": False},
            {"name": "val", "can_be_none": True},
        ]
        constraints = CodeConstraintBuilder.build_null_safety_constraints(variables)
        c = constraints[0]
        # If val is None and id is also None → violated
        assert c.satisfied(None, None) is False

    def test_multiple_non_nullable_and_nullable(self):
        """Should generate constraints for all pairs of non-nullable × nullable."""
        variables = [
            {"name": "a", "can_be_none": False},
            {"name": "b", "can_be_none": False},
            {"name": "c", "can_be_none": True},
            {"name": "d", "can_be_none": True},
        ]
        constraints = CodeConstraintBuilder.build_null_safety_constraints(variables)
        # 2 non-nullable × 2 nullable = 4 constraints
        assert len(constraints) == 4


class TestBuildTypeSafetyConstraints:
    """Tests for CodeConstraintBuilder.build_type_safety_constraints."""

    def test_generates_constraints_for_variable_pairs(self):
        """Should generate one constraint per unique pair of variables."""
        variables = [
            {"name": "x", "types": ["int"]},
            {"name": "y", "types": ["float"]},
        ]
        constraints = CodeConstraintBuilder.build_type_safety_constraints(variables)
        assert len(constraints) == 1
        assert isinstance(constraints[0], Constraint)

    def test_type_compatible_int_float(self):
        """int should be compatible with float in the type lattice."""
        variables = [
            {"name": "x", "types": ["int"]},
            {"name": "y", "types": ["float"]},
        ]
        constraints = CodeConstraintBuilder.build_type_safety_constraints(variables)
        c = constraints[0]
        # "int" is compatible with "float" (int → {int, float, object, unknown})
        assert c.satisfied("int", "float") is True

    def test_type_incompatible_str_int(self):
        """str should not be compatible with int in the type lattice."""
        variables = [
            {"name": "x", "types": ["str"]},
            {"name": "y", "types": ["int"]},
        ]
        constraints = CodeConstraintBuilder.build_type_safety_constraints(variables)
        c = constraints[0]
        # "str" is not compatible with "int"
        assert c.satisfied("str", "int") is False

    def test_no_constraints_for_single_variable(self):
        """Should produce no constraints with a single variable."""
        variables = [{"name": "x", "types": ["int"]}]
        constraints = CodeConstraintBuilder.build_type_safety_constraints(variables)
        assert len(constraints) == 0

    def test_description_includes_type_info(self):
        """Constraint description should include type information."""
        variables = [
            {"name": "a", "types": ["int"]},
            {"name": "b", "types": ["str"]},
        ]
        constraints = CodeConstraintBuilder.build_type_safety_constraints(variables)
        assert "type_compatible" in constraints[0].description
        assert "a" in constraints[0].description
        assert "b" in constraints[0].description


class TestBuildDomainsFromCode:
    """Tests for CodeConstraintBuilder.build_domains_from_code."""

    def test_default_domains_without_analysis(self):
        """Should return default domains when analysis is None."""
        domains = CodeConstraintBuilder.build_domains_from_code(None)
        assert "return_type" in domains
        assert "input_type" in domains
        assert "nullability" in domains
        assert "operation" in domains
        assert "complexity" in domains
        assert isinstance(domains["complexity"], list)

    def test_default_domains_with_empty_dict(self):
        """Should return default domains when analysis is an empty dict."""
        domains = CodeConstraintBuilder.build_domains_from_code({})
        assert "return_type" in domains
        assert domains["return_type"] == ["int", "str", "float", "bool", "None", "list", "dict", "object"]

    def test_adds_variable_type_domains(self):
        """Should add type domains for variables with known annotations."""
        analysis = {
            "variables": [
                {"name": "count", "annotation": "int", "nullable": False},
                {"name": "label", "annotation": "str", "nullable": True},
            ]
        }
        domains = CodeConstraintBuilder.build_domains_from_code(analysis)
        assert "type_count" in domains
        assert "type_label" in domains
        assert domains["type_count"] == ["int", "str", "float", "bool", "None", "list", "dict", "object"]

    def test_adds_nullable_domains(self):
        """Should add nullability domains for nullable variables."""
        analysis = {
            "variables": [
                {"name": "val", "annotation": "str", "nullable": True},
            ]
        }
        domains = CodeConstraintBuilder.build_domains_from_code(analysis)
        assert "null_val" in domains
        assert domains["null_val"] == ["nullable", "non_null"]

    def test_skips_unknown_annotations(self):
        """Should not add type domain for variables with 'unknown' annotation."""
        analysis = {
            "variables": [
                {"name": "x", "annotation": "unknown", "nullable": False},
            ]
        }
        domains = CodeConstraintBuilder.build_domains_from_code(analysis)
        assert "type_x" not in domains

    def test_complexity_domain_range(self):
        """The complexity domain should be a range from 1 to 20."""
        domains = CodeConstraintBuilder.build_domains_from_code(None)
        assert domains["complexity"] == list(range(1, 21))
