"""
Z3 Type Lattice Mixin.

Provides the type compatibility lattice and helper methods:
- _TYPE_LATTICE: Type compatibility lattice constant
- _annotation_to_types: Parse type annotations into possible types
- _add_assign_compat: Assignment type compatibility constraint
- _add_binop_compat: Binary operation type compatibility constraint
- _add_compare_compat: Comparison type compatibility constraint
- _check_type_violations: Post-hoc type violation check
"""

import logging

try:
    import z3 as z3_module  # type: ignore[import-unresolved]
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3TypeLatticeMixin:
    """Mixin for type lattice constant and type compatibility helpers."""

    # Type compatibility lattice: subtype relationships
    # key = type, value = set of types that are compatible (assignable to) this type
    _TYPE_LATTICE = {
        "int": {"int", "float", "object", "unknown"},
        "float": {"float", "object", "unknown"},
        "str": {"str", "object", "unknown"},
        "bool": {"bool", "int", "float", "object", "unknown"},
        "list": {"list", "object", "unknown"},
        "dict": {"dict", "object", "unknown"},
        "None": {"None", "object", "unknown"},
        "object": {"object", "unknown"},
        "unknown": {"unknown"},
    }

    def _annotation_to_types(self, annotation):
        """
        Parse a type annotation string into a list of possible types.

        Handles: 'int', 'str', 'Optional[int]', 'int | None',
                 'Union[int, str]', 'list[int]', etc.
        """
        if not annotation or annotation == "unknown":
            return ["unknown"]

        types = []
        ann = str(annotation).strip()

        # Handle Optional[X] -> X, None
        if ann.startswith("Optional[") and ann.endswith("]"):
            inner = ann[9:-1]
            types.append(inner)
            types.append("None")
            return types

        # Handle Union[X, Y, ...] -> X, Y, ...
        if ann.startswith("Union[") and ann.endswith("]"):
            inner = ann[6:-1]
            for part in inner.split(","):
                part = part.strip()
                if part == "None":
                    types.append("None")
                else:
                    types.append(part)
            return types

        # Handle X | None (PEP 604)
        if "|" in ann:
            for part in ann.split("|"):
                part = part.strip()
                if part == "None":
                    types.append("None")
                else:
                    types.append(part)
            return types

        # Handle list[X], dict[X, Y] -> just the outer type
        if ann.startswith("list["):
            types.append("list")
            return types
        if ann.startswith("dict["):
            types.append("dict")
            return types

        # Simple type
        types.append(ann)
        return types

    def _add_assign_compat(
        self, solver, type_sort, type_name_to_const,
        left_var, right_var, left_type, right_type,
    ):
        """
        Add assignment compatibility constraint:
        right_type must be assignable to left_type per the type lattice.
        """
        # Get compatible types for the left-hand side
        compatible = self._TYPE_LATTICE.get(left_type, {"unknown"})
        # The right variable must have a type that is in the compatible set
        compat_consts = [
            type_name_to_const[t]
            for t in compatible
            if t in type_name_to_const
        ]
        if compat_consts:
            solver.add(
                z3_module.Or(*[right_var == c for c in compat_consts])
            )

    def _add_binop_compat(
        self, solver, type_sort, type_name_to_const,
        left_var, right_var, op,
    ):
        """
        Add binary operation type compatibility constraint.
        Numeric ops require numeric types; string concat requires strings.
        """
        if op in ("add", "+"):
            # Addition: both must be numeric OR both must be str
            numeric = {"int", "float", "bool"}
            numeric_consts = [
                type_name_to_const[t]
                for t in numeric
                if t in type_name_to_const
            ]
            str_consts = [
                type_name_to_const[t]
                for t in {"str"}
                if t in type_name_to_const
            ]
            if numeric_consts and str_consts:
                solver.add(
                    z3_module.Or(
                        z3_module.And(
                            z3_module.Or(*[left_var == c for c in numeric_consts]),
                            z3_module.Or(*[right_var == c for c in numeric_consts]),
                        ),
                        z3_module.And(
                            z3_module.Or(*[left_var == c for c in str_consts]),
                            z3_module.Or(*[right_var == c for c in str_consts]),
                        ),
                    )
                )
            elif numeric_consts:
                solver.add(
                    z3_module.And(
                        z3_module.Or(*[left_var == c for c in numeric_consts]),
                        z3_module.Or(*[right_var == c for c in numeric_consts]),
                    )
                )
        else:
            # Sub, mul, div: both must be numeric
            numeric = {"int", "float", "bool"}
            numeric_consts = [
                type_name_to_const[t]
                for t in numeric
                if t in type_name_to_const
            ]
            if numeric_consts:
                solver.add(
                    z3_module.And(
                        z3_module.Or(*[left_var == c for c in numeric_consts]),
                        z3_module.Or(*[right_var == c for c in numeric_consts]),
                    )
                )

    def _add_compare_compat(
        self, solver, type_sort, type_name_to_const,
        left_var, right_var,
    ):
        """
        Add comparison type compatibility: both sides must be
        of comparable types (same type family).
        """
        # Group types into comparable families
        families = [
            {"int", "float", "bool"},
            {"str"},
            {"list"},
            {"dict"},
        ]

        family_constraints = []
        for family in families:
            family_consts = [
                type_name_to_const[t]
                for t in family
                if t in type_name_to_const
            ]
            if family_consts:
                family_constraints.append(
                    z3_module.And(
                        z3_module.Or(*[left_var == c for c in family_consts]),
                        z3_module.Or(*[right_var == c for c in family_consts]),
                    )
                )

        if family_constraints:
            solver.add(z3_module.Or(*family_constraints))

    def _check_type_violations(self, assignment, operations):
        """Post-hoc check of a type assignment against operations."""
        violations = []
        for op_info in operations:
            left = op_info.get("left_var", "")
            right = op_info.get("right_var", "")
            op = op_info.get("op", "")

            left_type = assignment.get(left, "unknown")
            right_type = assignment.get(right, "unknown")

            if op in ("assign", "="):
                compat = self._TYPE_LATTICE.get(left_type, {"unknown"})
                if right_type not in compat:
                    violations.append(
                        f"Type mismatch in assignment: {right_type} -> {left} "
                        f"(expected one of {compat})"
                    )
            elif op in ("add", "+"):
                numeric = {"int", "float", "bool"}
                if not (
                    (left_type in numeric and right_type in numeric)
                    or (left_type == "str" and right_type == "str")
                ):
                    violations.append(
                        f"Incompatible types for +: {left_type} + {right_type}"
                    )
            elif op in ("sub", "-", "mul", "*", "div", "/"):
                numeric = {"int", "float", "bool"}
                if left_type not in numeric or right_type not in numeric:
                    violations.append(
                        f"Incompatible types for {op}: {left_type}, {right_type}"
                    )

        return violations
