"""
Z3 Invariant Patterns Mixin.

Provides AST-based invariant extraction and verification methods:
- _z3_prove_code_invariants: AST-extracted invariant verification
- _z3_prove_pattern_invariants: Pattern-based invariant extraction and verification
"""

import ast
import gc
import logging

try:
    import z3 as z3_module  # type: ignore[import-unresolved]
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3InvariantPatternsMixin:
    """Mixin for code-invariant and pattern-invariant verification using Z3."""

    def _z3_prove_code_invariants(self, invariants_info, variables_info):
        """
        Prove invariants extracted from AST analysis using Z3.

        Handles common invariant patterns:
        - index_bounds: array index >= 0 and < len
        - no_div_zero: denominator != 0
        - not_null: variable != None
        - range: variable in [low, high]
        """
        try:
            solver = z3_module.Solver()
            solver.set("timeout", self.timeout_ms)

            z3_vars = {}
            for inv in invariants_info:
                kind = inv.get("kind", "")
                inv_vars = inv.get("variables", [])

                for var_name in inv_vars:
                    if var_name not in z3_vars:
                        z3_vars[var_name] = z3_module.Int(var_name)

                if kind == "index_bounds":
                    # 0 <= index < len (assume len is a large constant)
                    # Try to find a violation: index < 0 or index >= len
                    for var_name in inv_vars:
                        if var_name in z3_vars:
                            solver.add(z3_module.Or(z3_vars[var_name] < 0, z3_vars[var_name] >= 1000000))

                elif kind == "no_div_zero":
                    for var_name in inv_vars:
                        if var_name in z3_vars:
                            solver.add(z3_vars[var_name] == 0)
                            # Trying to find a model where divisor = 0

                elif kind == "not_null":
                    null_sort, null_consts = z3_module.EnumSort(
                        self._unique_sort_name("NullCheck"), ["IS_NULL", "NOT_NULL"]
                    )
                    for var_name in inv_vars:
                        z3_null_var = z3_module.Const(
                            f"nullcheck_{var_name}", null_sort
                        )
                        solver.add(z3_null_var == null_consts[0])  # IS_NULL

                elif kind == "range":
                    low = inv.get("low", 0)
                    high = inv.get("high", 100)
                    for var_name in inv_vars:
                        if var_name in z3_vars:
                            solver.add(z3_module.Or(z3_vars[var_name] < low, z3_vars[var_name] > high))

            # Check if any violation is reachable
            result = solver.check()

            if result == z3_module.unsat:
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_INVARIANT",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "Z3 proved all code invariants hold",
                }
            elif result == z3_module.sat:
                model = solver.model()
                counterexample = {}
                for var_name, z3_var in z3_vars.items():
                    val = model.eval(z3_var)
                    counterexample[var_name] = str(val)
                return {
                    "status": "VIOLATED",
                    "solver_type": "Z3_INVARIANT",
                    "verified": False,
                    "counterexamples": [counterexample],
                    "proof": f"Z3 found invariant violation: {counterexample}",
                }
            else:
                return {
                    "status": "UNKNOWN",
                    "solver_type": "Z3_INVARIANT",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Z3 returned unknown for code invariants",
                }

        except Exception as e:
            logger.error("Z3 code invariant proof error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3_INVARIANT", "message": str(e)}
        finally:
            gc.collect()

    def _z3_prove_pattern_invariants(self, raw_code, variables_info):
        """
        Extract invariant patterns from raw code and verify with Z3.

        Detects common patterns:
        - Division operations -> divisor != 0 invariant
        - Index operations -> index >= 0 invariant
        - Comparisons with None -> not_null invariant
        """
        try:
            invariants = []

            # Parse and walk the AST to find invariant patterns
            try:
                tree = ast.parse(raw_code)
            except SyntaxError:
                return {
                    "status": "UNKNOWN",
                    "solver_type": "Z3_PATTERN",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Cannot parse code for pattern invariant extraction",
                }

            # Collect nodes that are inside annotations (to skip them)
            annotation_nodes = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.AnnAssign, ast.arg)):
                    if hasattr(node, 'annotation') and node.annotation:
                        for sub in ast.walk(node.annotation):
                            annotation_nodes.add(id(sub))

            for node in ast.walk(tree):
                # Skip nodes inside type annotations
                if id(node) in annotation_nodes:
                    continue

                # Division -> no_div_zero
                if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Div, ast.FloorDiv)
                ):
                    if isinstance(node.right, ast.Name):
                        invariants.append({
                            "kind": "no_div_zero",
                            "variables": [node.right.id],
                        })
                    elif isinstance(node.right, ast.Constant) and node.right.value == 0:
                        invariants.append({
                            "kind": "no_div_zero_literal",
                            "variables": [],
                            "proof": "Literal division by zero detected",
                        })

                # Subscript -> index_bounds (but not in annotations)
                if isinstance(node, ast.Subscript) and id(node) not in annotation_nodes:
                    if isinstance(node.slice, ast.Name):
                        invariants.append({
                            "kind": "index_bounds",
                            "variables": [node.slice.id],
                        })
                    elif isinstance(node.slice, ast.Constant):
                        idx_val = node.slice.value
                        if isinstance(idx_val, int) and idx_val < 0:
                            invariants.append({
                                "kind": "negative_index",
                                "variables": [],
                                "proof": f"Negative index {idx_val} detected",
                            })

                # Compare with None -> not_null
                if isinstance(node, ast.Compare):
                    for comp in node.comparators:
                        if isinstance(comp, ast.Constant) and comp.value is None:
                            if isinstance(node.left, ast.Name):
                                invariants.append({
                                    "kind": "not_null",
                                    "variables": [node.left.id],
                                })

            if not invariants:
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_PATTERN",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "No invariant patterns detected in code",
                }

            return self._z3_prove_code_invariants(invariants, variables_info)

        except Exception as e:
            logger.error("Z3 pattern invariant error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3_PATTERN", "message": str(e)}
