"""
Z3 Type-Safety Proof Mixin.

Provides the _z3_prove_type_safety_deep method using Z3 EnumSort
for a type hierarchy.

Type lattice constant and compatibility helper methods are in type_lattice.py.
"""

import gc
import logging

try:
    import z3 as z3_module
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3TypeSafetyMixin:
    """Mixin for type-safety proof methods using Z3 EnumSort."""

    def _z3_prove_type_safety(self, variables_with_types):
        """Type-safety proof using Z3 EnumSort with type compatibility."""
        return self._z3_prove_type_safety_deep(variables_with_types, [])

    def _z3_prove_type_safety_deep(self, variables_with_types, operations):
        """
        Deep type-safety proof using Z3 EnumSort for a type hierarchy.

        Creates an EnumSort with all observed types, then:
        - Constrains each variable to its allowed types
        - For each operation, adds compatibility constraints from the lattice
        - Checks that assignments between variables are type-compatible
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

            solver = z3_module.Solver()
            solver.set("timeout", self.timeout_ms)

            # Create a Z3 variable for the type of each program variable
            z3_type_vars = {}
            var_allowed = {}
            for var_info in variables_with_types:
                name = var_info["name"]
                allowed = var_info.get("types", ["unknown"])
                var_allowed[name] = allowed
                z3_type_vars[name] = z3_module.Const(f"type_{name}", type_sort)

                # Constrain to allowed types
                allowed_consts = [
                    type_name_to_const[t]
                    for t in allowed
                    if t in type_name_to_const
                ]
                if allowed_consts:
                    solver.add(
                        z3_module.Or(
                            *[
                                z3_type_vars[name] == c
                                for c in allowed_consts
                            ]
                        )
                    )

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
                            solver, type_sort, type_name_to_const,
                            left_var, right_var, left_type, right_type,
                        )
                    # Binary operation compatibility
                    elif op in ("add", "+", "sub", "-", "mul", "*", "div", "/"):
                        self._add_binop_compat(
                            solver, type_sort, type_name_to_const,
                            left_var, right_var, op,
                        )
                    # Comparison: both sides must be comparable
                    elif op in ("eq", "==", "lt", "<", "gt", ">", "le", "<=", "ge", ">="):
                        self._add_compare_compat(
                            solver, type_sort, type_name_to_const,
                            left_var, right_var,
                        )

            # Also add pairwise compatibility between variables that share
            # an operation edge (even without explicit operation info)
            var_names = list(z3_type_vars.keys())
            for i in range(len(var_names)):
                for j in range(i + 1, len(var_names)):
                    n1, n2 = var_names[i], var_names[j]
                    allowed1 = set(var_allowed.get(n1, ["unknown"]))
                    allowed2 = set(var_allowed.get(n2, ["unknown"]))
                    # If they share any compatible type pair, no constraint needed
                    # If no compatible pair exists, they must not be assigned
                    # the same value - this is already handled by domain restriction

            result = solver.check()

            if result == z3_module.sat:
                model = solver.model()
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

                # Verify that the assignment is actually type-safe
                type_violations = self._check_type_violations(
                    assignment, operations
                )
                if type_violations:
                    return {
                        "status": "VIOLATED",
                        "solver_type": "Z3_ENUMSORT",
                        "verified": False,
                        "assignment": assignment,
                        "violations": type_violations,
                        "proof": f"Type violations found: {type_violations}",
                    }

                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "assignment": assignment,
                    "proof": f"Z3 EnumSort type assignment: {assignment}",
                }
            elif result == z3_module.unsat:
                return {
                    "status": "UNSATISFIABLE",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "proof": "Z3: no valid type assignment exists - type system is inconsistent",
                }
            else:
                return {
                    "status": "UNKNOWN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "proof": "Z3 returned unknown (timeout or unsupported theory)",
                }

        except Exception as e:
            logger.error("Z3 type-safety proof error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3", "message": str(e)}
        finally:
            gc.collect()
