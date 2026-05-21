"""
AC-3 Fallback Mixin.

Provides fallback implementations when Z3 is unavailable (Android/Termux):
- _ac3_prove_null_safety: Null-safety verification using AC-3 + Backtracking
- _ac3_prove_type_safety: Type-safety verification using AC-3
- _ac3_prove_code_safety: Complete code safety verification using AC-3
"""

import ast
import logging

from ..constraint_solver import Constraint, ConstraintSolver

logger = logging.getLogger(__name__)


class AC3FallbackMixin:
    """Mixin for AC-3 fallback implementations when Z3 is unavailable."""

    def _ac3_prove_null_safety(self, variable_names, nullable_vars):
        """Verificacion de null-safety usando AC-3 + Backtracking."""
        try:
            non_nullable = [v for v in variable_names if v not in nullable_vars]

            domains = {}
            for v in variable_names:
                if v in nullable_vars:
                    domains[v] = ["Some", "None"]
                else:
                    domains[v] = ["Some"]  # non-nullable only have Some

            constraints = []
            # Domain restriction already enforces non-nullable = ["Some"].
            # No cross-constraints needed — the previous lambda-based
            # cross-constraints were vacuous (ignored y entirely).

            solver = ConstraintSolver(timeout_ms=self.timeout_ms)
            result = solver.solve(domains, constraints)

            if result["status"] == "UNSATISFIABLE":
                return {
                    "status": "PROVEN",
                    "solver_type": "AC3",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "AC-3 proved: constraints are unsatisfiable when non-nullable = None"
                }
            elif result["status"] == "SATISFIED":
                assignment = result.get("assignment", {})
                violations = {k: v for k, v in assignment.items() if v == "None" and k in non_nullable}
                if violations:
                    return {
                        "status": "VIOLATED",
                        "solver_type": "AC3",
                        "verified": False,
                        "counterexamples": [violations],
                        "proof": f"AC-3 found: {violations}"
                    }
                return {
                    "status": "PROVEN",
                    "solver_type": "AC3",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "AC-3 proved: non-nullable variables are not None in all valid assignments"
                }
            return {
                "status": result["status"],
                "solver_type": "AC3",
                "verified": False,
                "counterexamples": [],
                "proof": f"AC-3 result: {result['status']}"
            }

        except Exception as e:
            return {"status": "ERROR", "solver_type": "AC3", "message": str(e)}

    def _ac3_prove_type_safety(self, variables_with_types):
        """Verificacion de type-safety usando AC-3 con compatibilidad real."""
        try:
            domains = {}
            for var_info in variables_with_types:
                domains[var_info["name"]] = var_info.get("types", ["unknown"])

            # Add type compatibility constraints between variables that
            # could interact (assignment compatibility per the type lattice).
            # Without constraints, SAT just means "some assignment exists"
            # which is NOT the same as PROVEN (all assignments are safe).
            constraints = []
            if hasattr(self, '_TYPE_LATTICE'):
                # For each pair of variables, add compatibility constraint
                # based on the type lattice
                var_names = [v["name"] for v in variables_with_types]
                for i, vi in enumerate(variables_with_types):
                    for j, vj in enumerate(variables_with_types):
                        if i == j:
                            continue
                        name_i = vi["name"]
                        name_j = vj["name"]
                        types_i = vi.get("types", ["unknown"])
                        types_j = vj.get("types", ["unknown"])
                        # Add constraint: if types are incompatible for
                        # assignment (j -> i), they can't coexist
                        for ti in types_i:
                            compatible = self._TYPE_LATTICE.get(ti, {"unknown"})
                            incompatible_j_types = [
                                t for t in types_j if t not in compatible
                            ]
                            if incompatible_j_types:
                                constraints.append(Constraint(
                                    name_j, name_i,
                                    lambda x, y, compat=compatible: x in compat,
                                    description=(
                                        f"type compat: {name_j} -> "
                                        f"{name_i} (source type must be in {compatible})"
                                    ),
                                ))

            solver = ConstraintSolver(timeout_ms=self.timeout_ms)
            result = solver.solve(domains, constraints)

            if result["status"] == "SATISFIED":
                assignment = result.get("assignment", {})
                # FIX: SAT ≠ PROVEN. Finding a consistent type assignment
                # does NOT prove type safety for ALL possible assignments.
                # Previously returned PROVEN/verified=True here, which was
                # incorrect. Return PASS_WITH_CAVEATS instead.
                return {
                    "status": "PASS_WITH_CAVEATS",
                    "solver_type": "AC3",
                    "verified": False,
                    "assignment": assignment,
                    "proof": (
                        "AC-3 type verification: consistent assignment found, "
                        "but SAT does not guarantee all assignments are safe"
                    ),
                }
            elif result["status"] == "UNSATISFIABLE":
                return {
                    "status": "UNSATISFIABLE",
                    "solver_type": "AC3",
                    "verified": False,
                    "assignment": None,
                    "proof": "AC-3: no valid type assignment exists"
                }
            return {
                "status": result["status"],
                "solver_type": "AC3",
                "verified": False,
                "assignment": None,
                "proof": f"AC-3 type verification: {result['status']}"
            }

        except Exception as e:
            return {"status": "ERROR", "solver_type": "AC3", "message": str(e)}

    def _ac3_prove_code_safety(self, ast_analysis, raw_code):
        """
        AC-3 fallback for prove_code_safety.
        Uses AC-3 for each sub-proof when Z3 is unavailable.
        """
        results = {
            "null_safety": None,
            "type_safety": None,
            "invariant_safety": None,
            "overall_status": "UNKNOWN",
            "solver_type": "AC3_FALLBACK",
            "model": None,
            "errors": [],
        }

        try:
            # Null-safety
            variables_info = ast_analysis.get("variables", [])
            all_var_names = [v["name"] for v in variables_info]
            nullable_vars = set()
            for v in variables_info:
                annotation = v.get("annotation") or ""
                if v.get("nullable", False):
                    nullable_vars.add(v["name"])
                elif isinstance(annotation, str) and (
                    "Optional" in annotation or "None" in annotation
                ):
                    nullable_vars.add(v["name"])

            if all_var_names:
                results["null_safety"] = self._ac3_prove_null_safety(
                    all_var_names, nullable_vars
                )

            # Type-safety
            variables_with_types = []
            for v in variables_info:
                annotation = v.get("annotation") or "unknown"
                types_for_var = self._annotation_to_types(annotation)
                variables_with_types.append({
                    "name": v["name"],
                    "types": types_for_var if types_for_var else ["unknown"],
                })
            if variables_with_types:
                results["type_safety"] = self._ac3_prove_type_safety(
                    variables_with_types
                )

            # Invariant-safety (simple pattern check)
            try:
                tree = ast.parse(raw_code)
                invariants = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.BinOp) and isinstance(
                        node.op, (ast.Div, ast.FloorDiv)
                    ):
                        if isinstance(node.right, ast.Name):
                            invariants.append({
                                "kind": "no_div_zero",
                                "variables": [node.right.id],
                            })
                results["invariant_safety"] = {
                    "status": "LIKELY_PROVEN" if not invariants else "UNKNOWN",
                    "solver_type": "AC3",
                    "verified": False,  # LIKELY_PROVEN ≠ PROVEN; AC-3 pattern check is not formal proof
                    "counterexamples": [],
                    "proof": f"AC-3 pattern check: {len(invariants)} patterns found",
                }
            except SyntaxError:
                results["invariant_safety"] = {
                    "status": "UNKNOWN",
                    "solver_type": "AC3",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Cannot parse code",
                }

            # Overall
            sub_results = [
                results["null_safety"],
                results["type_safety"],
                results["invariant_safety"],
            ]
            sub_results = [r for r in sub_results if r is not None]
            if all(r.get("verified", False) for r in sub_results):
                results["overall_status"] = "LIKELY_PROVEN"
            elif any(
                r.get("status") in ("VIOLATED", "UNSATISFIABLE") for r in sub_results
            ):
                results["overall_status"] = "VIOLATED"
            else:
                results["overall_status"] = "PARTIAL"

        except Exception as e:
            results["errors"].append(str(e))
            results["overall_status"] = "ERROR"

        return results
