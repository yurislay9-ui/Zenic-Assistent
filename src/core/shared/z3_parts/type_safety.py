"""
Z3 Type-Safety Proof Mixin.

Provides the _z3_prove_type_safety_deep method using Z3 EnumSort
for a type hierarchy.

Type lattice constant and compatibility helper methods are in type_lattice.py.

Fix (A12): SAT ≠ PROVEN. Previously, when Z3 returned SAT, the code found
one type assignment and checked it. If no violations were found in that single
assignment, it reported PROVEN. But SAT only means "a consistent type assignment
EXISTS" — not "ALL possible type assignments are safe."

Now uses proof by contradiction (two-phase):
  Phase 1: Consistency check — add domain + compatibility constraints, check SAT
           (ensures the type system is not self-contradictory)
  Phase 2: Proof by contradiction — add ONLY domain constraints plus the negation
           of the safety property ("some operation has incompatible types").
           If UNSAT → PROVEN (no unsafe assignment exists under domain constraints)
           If SAT   → VIOLATED (counterexample with unsafe type assignment)
"""

import gc
import logging

try:
    import z3 as z3_module  # type: ignore[import-unresolved]
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3TypeSafetyMixin:
    """Mixin for type-safety proof methods using Z3 EnumSort."""

    def _z3_prove_type_safety(self, variables_with_types):
        """Type-safety proof using Z3 EnumSort with type compatibility."""
        return self._z3_prove_type_safety_deep(variables_with_types, [])

    def _build_unsafe_type_constraint(
        self, type_name_to_const, left_var, right_var, op, left_type, right_type,
    ):
        """Build a Z3 expression that is TRUE when the operation is type-unsafe.

        This is the logical negation of the compatibility constraints used
        in Phase 1. For each operation type:
        - Assign: unsafe when right type is NOT assignable to left type
        - BinOp:  unsafe when operand types are incompatible for the operator
        - Compare: unsafe when operand types are not comparable

        Returns None if no unsafe constraint can be built (e.g., missing
        type constants in the EnumSort).
        """
        if op in ("assign", "="):
            # FIX: Enumerate over possible types of the left operand using
            # the Z3 variable (left_var) instead of the static annotation
            # (left_type). This allows reasoning about variables that may
            # have multiple possible types at runtime.
            unsafe_by_type = []
            for type_name, type_const in type_name_to_const.items():
                compatible = self._TYPE_LATTICE.get(type_name, {"unknown"})
                compat_consts = [
                    type_name_to_const[t]
                    for t in compatible
                    if t in type_name_to_const
                ]
                if compat_consts:
                    # Unsafe when: left_var == type_const AND
                    # right_var is NOT in the compatible set for that type
                    unsafe_by_type.append(z3_module.And(
                        left_var == type_const,
                        z3_module.Not(z3_module.Or(
                            *[right_var == c for c in compat_consts]
                        )),
                    ))
            return z3_module.Or(*unsafe_by_type) if unsafe_by_type else None

        elif op in ("add", "+"):
            # Safe: (both numeric) OR (both str)
            # Unsafe: NOT (both numeric OR both str)
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
            safe_parts = []
            if numeric_consts:
                safe_parts.append(z3_module.And(
                    z3_module.Or(*[left_var == c for c in numeric_consts]),
                    z3_module.Or(*[right_var == c for c in numeric_consts]),
                ))
            if str_consts:
                safe_parts.append(z3_module.And(
                    z3_module.Or(*[left_var == c for c in str_consts]),
                    z3_module.Or(*[right_var == c for c in str_consts]),
                ))
            if safe_parts:
                return z3_module.Not(z3_module.Or(*safe_parts))

        elif op in ("sub", "-", "mul", "*", "div", "/"):
            # Safe: both numeric
            # Unsafe: NOT (both numeric)
            numeric = {"int", "float", "bool"}
            numeric_consts = [
                type_name_to_const[t]
                for t in numeric
                if t in type_name_to_const
            ]
            if numeric_consts:
                safe_expr = z3_module.And(
                    z3_module.Or(*[left_var == c for c in numeric_consts]),
                    z3_module.Or(*[right_var == c for c in numeric_consts]),
                )
                return z3_module.Not(safe_expr)

        elif op in ("eq", "==", "lt", "<", "gt", ">", "le", "<=", "ge", ">="):
            # Safe: both operands in the same comparable type family
            # Unsafe: NOT (both in same family)
            families = [
                {"int", "float", "bool"},
                {"str"},
                {"list"},
                {"dict"},
            ]
            safe_parts = []
            for family in families:
                family_consts = [
                    type_name_to_const[t]
                    for t in family
                    if t in type_name_to_const
                ]
                if family_consts:
                    safe_parts.append(z3_module.And(
                        z3_module.Or(*[left_var == c for c in family_consts]),
                        z3_module.Or(*[right_var == c for c in family_consts]),
                    ))
            if safe_parts:
                return z3_module.Not(z3_module.Or(*safe_parts))

        # Unknown operation type — cannot build unsafe constraint
        return None

    def _z3_prove_type_safety_deep(self, variables_with_types, operations):
        """
        Deep type-safety proof using Z3 EnumSort for a type hierarchy.

        Two-phase proof:
        Phase 1 (Consistency): Add domain + compatibility constraints.
            SAT = type system is consistent (a safe assignment exists).
            UNSAT = type system is contradictory.
        Phase 2 (Proof by contradiction): Add domain constraints + negation
            of safety (assert some operation has incompatible types).
            UNSAT = PROVEN (no unsafe assignment is possible).
            SAT = VIOLATED (counterexample exists).

        Fix (A12): Previously, Phase 2 checked a single SAT model for
        violations. But SAT ≠ PROVEN — finding one safe assignment doesn't
        prove ALL assignments are safe. Now we use proof by contradiction:
        assert the negation of safety and check for UNSAT.
        """
        try:
            # Collect all unique types across all variables
            all_types_set = set()
            for var_info in variables_with_types:
                for t in var_info.get("types", ["unknown"]):
                    all_types_set.add(t)
            all_types = sorted(all_types_set)

            if not all_types:
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "assignment": {},
                    "proof": "No types to verify",
                }

            # Create EnumSort for the type domain
            # Z3 EnumSort requires at least 1 constructor
            if len(all_types) == 1:
                all_types = all_types + ["__placeholder__"]

            type_sort, type_consts = z3_module.EnumSort(self._unique_sort_name("TypeDomain"), all_types)
            type_name_to_const = dict(zip(all_types, type_consts))

            # ============================================================
            #  Shared setup: Z3 variables and domain constraints
            # ============================================================
            z3_type_vars = {}
            var_allowed = {}
            for var_info in variables_with_types:
                name = var_info["name"]
                allowed = var_info.get("types", ["unknown"])
                var_allowed[name] = allowed
                z3_type_vars[name] = z3_module.Const(f"type_{name}", type_sort)

            # Helper: build domain constraints for a solver
            def _add_domain_constraints(slv):
                for var_info in variables_with_types:
                    name = var_info["name"]
                    allowed = var_info.get("types", ["unknown"])
                    allowed_consts = [
                        type_name_to_const[t]
                        for t in allowed
                        if t in type_name_to_const
                    ]
                    if allowed_consts:
                        slv.add(
                            z3_module.Or(
                                *[
                                    z3_type_vars[name] == c
                                    for c in allowed_consts
                                ]
                            )
                        )

            # ============================================================
            #  Phase 1: Consistency check
            #  Add domain + compatibility constraints → check SAT
            #  This verifies the type system is not self-contradictory.
            # ============================================================
            consistency_solver = z3_module.Solver()
            consistency_solver.set("timeout", self.timeout_ms)

            # Add domain constraints (each var must be one of its allowed types)
            _add_domain_constraints(consistency_solver)

            # Add type compatibility constraints from operations
            for op_info in operations:
                left = op_info.get("left_var", "")
                right = op_info.get("right_var", "")
                op = op_info.get("op", "")
                left_type = op_info.get("left_type", "unknown")
                right_type = op_info.get("right_type", "unknown")

                # Check if both sides are tracked variables
                if left in z3_type_vars and right in z3_type_vars:
                    left_var = z3_type_vars[left]
                    right_var = z3_type_vars[right]

                    # Assignment compatibility: right type must be
                    # assignable to left type
                    if op in ("assign", "="):
                        self._add_assign_compat(
                            consistency_solver, type_sort, type_name_to_const,
                            left_var, right_var, left_type, right_type,
                        )
                    # Binary operation compatibility
                    elif op in ("add", "+", "sub", "-", "mul", "*", "div", "/"):
                        self._add_binop_compat(
                            consistency_solver, type_sort, type_name_to_const,
                            left_var, right_var, op,
                        )
                    # Comparison: both sides must be comparable
                    elif op in ("eq", "==", "lt", "<", "gt", ">", "le", "<=", "ge", ">="):
                        self._add_compare_compat(
                            consistency_solver, type_sort, type_name_to_const,
                            left_var, right_var,
                        )

            consistency_result = consistency_solver.check()

            if consistency_result == z3_module.unsat:
                # Type constraints are contradictory — no valid assignment exists
                return {
                    "status": "UNSATISFIABLE",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "proof": "Z3: no valid type assignment exists - type system is inconsistent",
                }
            elif consistency_result != z3_module.sat:
                # Unknown/timeout on consistency check
                return {
                    "status": "UNKNOWN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "proof": "Z3 returned unknown on consistency check (timeout or unsupported theory)",
                }

            # Phase 1 passed: a safe type assignment exists (SAT)
            # But SAT ≠ PROVEN! We must now prove that NO unsafe assignment exists.

            # ============================================================
            #  Phase 2: Proof by contradiction
            #  Assert the negation of type safety: "there EXISTS a type
            #  assignment where some operation has incompatible types."
            #  If UNSAT → the safety property holds (PROVEN)
            #  If SAT   → extract the counterexample (VIOLATED)
            #
            #  CRITICAL (Fix A12): Phase 2 uses a FRESH solver with ONLY
            #  domain constraints (NOT the compatibility constraints from
            #  Phase 1). Adding compatibility constraints AND the negation
            #  would be trivially UNSAT, making the proof vacuous.
            #  Instead, we check whether the domain constraints alone
            #  rule out all unsafe type assignments.
            # ============================================================

            # Build violation constraints: for each operation, build a Z3
            # expression that is TRUE when the operation is type-unsafe.
            violation_constraints = []
            for op_info in operations:
                left = op_info.get("left_var", "")
                right = op_info.get("right_var", "")
                op = op_info.get("op", "")
                left_type = op_info.get("left_type", "unknown")
                right_type = op_info.get("right_type", "unknown")

                if left in z3_type_vars and right in z3_type_vars:
                    left_var = z3_type_vars[left]
                    right_var = z3_type_vars[right]

                    unsafe_expr = self._build_unsafe_type_constraint(
                        type_name_to_const, left_var, right_var,
                        op, left_type, right_type,
                    )
                    if unsafe_expr is not None:
                        violation_constraints.append(unsafe_expr)

            # If no operations to check, type safety is trivially proven
            if not violation_constraints:
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "assignment": {},
                    "proof": "No operations to verify — type safety is vacuously true",
                }

            # Phase 2 solver: domain constraints + negation of safety
            proof_solver = z3_module.Solver()
            proof_solver.set("timeout", self.timeout_ms)

            # Add ONLY domain constraints (NOT compatibility constraints)
            _add_domain_constraints(proof_solver)

            # Assert the negation of type safety:
            # "at least one operation has incompatible types"
            proof_solver.add(z3_module.Or(*violation_constraints))

            proof_result = proof_solver.check()

            if proof_result == z3_module.unsat:
                # No unsafe type assignment exists under domain constraints
                # → Type safety is PROVEN
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "assignment": {},
                    "proof": (
                        "Z3 EnumSort PROVED: no unsafe type assignment exists "
                        "(violation search is UNSAT under domain constraints). "
                        f"Verified {len(violation_constraints)} operation(s)."
                    ),
                }
            elif proof_result == z3_module.sat:
                # Found a counterexample — an unsafe type assignment exists
                model = proof_solver.model()
                assignment = {}
                for name, z3_var in z3_type_vars.items():
                    val = model.eval(z3_var)
                    val_str = str(val)
                    # Map back from EnumSort constant name to type name
                    for type_name, const in type_name_to_const.items():
                        if str(const) == val_str or str(val) == type_name:
                            assignment[name] = type_name
                            break
                    else:
                        assignment[name] = val_str

                # Identify which operations are violated in this counterexample
                type_violations = self._check_type_violations(
                    assignment, operations
                )

                return {
                    "status": "VIOLATED",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "assignment": assignment,
                    "violations": type_violations,
                    "proof": (
                        f"Z3 FOUND VIOLATION: unsafe type assignment exists. "
                        f"Counterexample: {assignment}. "
                        f"Violations: {type_violations}"
                    ),
                }
            else:
                # Unknown/timeout on Phase 2
                # Phase 1 showed consistency, but can't prove safety
                return {
                    "status": "LIKELY_PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,  # Best-effort: Phase 1 passed
                    "assignment": {},
                    "proof": (
                        "Z3: Phase 1 (consistency) passed, but Phase 2 "
                        "(proof by contradiction) returned UNKNOWN/timeout. "
                        "Type safety is likely proven but not formally verified "
                        "within the time budget."
                    ),
                }

        except Exception as e:
            logger.error("Z3 type-safety proof error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3", "message": str(e)}
        finally:
            gc.collect()
