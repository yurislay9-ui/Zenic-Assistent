"""
ZENIC-AGENTS - Concrete Input Generation Mixin

Concrete input generation methods for the SymbolicExecutor:
- generate_concrete_inputs: Generate concrete inputs from Z3 model
- _generate_z3_concrete_inputs: Z3-based concrete input generation
- _generate_heuristic_inputs: Heuristic-based fallback input generation
- prove_violation_reachable: Z3 formal proof of violation reachability
- _violation_to_z3_condition: Convert violation string to Z3 constraint
- export_path_conditions_smt: Export path conditions as SMT-LIB2

This module provides a mixin class that is composed into SymbolicExecutor.
"""

import logging

logger = logging.getLogger(__name__)

from ..z3_solver import HAS_Z3

# Z3 module reference for convenience (only available when HAS_Z3 is True)
if HAS_Z3:
    import z3 as z3_module

from .types import SymbolicValue


class ConcreteGenMixin:
    """
    Mixin for SymbolicExecutor providing concrete input generation,
    violation reachability proof, and SMT export methods.
    """

    # ================================================================
    #  Deep Symbolic Analysis: Counterexample & Test Generation
    # ================================================================

    def generate_concrete_inputs(self, path):
        """
        Generate concrete input values from a Z3 model for a feasible path.

        Given a SymbolicPath with Z3 conditions, uses the Z3 solver to find
        a concrete model (assignment of values to variables) that satisfies
        all path conditions. This produces actual test inputs that would
        exercise this specific execution path.

        Returns:
            dict with:
                - 'inputs': dict of {var_name: concrete_value}
                - 'model_str': human-readable model string
                - 'smt_lib': SMT-LIB2 representation of path conditions
                - 'feasible': bool
                - 'proven_with': 'Z3' or 'STRING_HEURISTIC'
        """
        if not path.z3_conditions and not path.condition:
            return {
                "inputs": {},
                "model_str": "empty_path",
                "smt_lib": "",
                "feasible": True,
                "proven_with": "TRIVIAL",
            }

        if HAS_Z3 and path.z3_conditions:
            return self._generate_z3_concrete_inputs(path)
        return self._generate_heuristic_inputs(path)

    def _generate_z3_concrete_inputs(self, path):
        """
        Use Z3 to find a concrete model satisfying all path conditions.

        Produces actual test inputs and an SMT-LIB2 formula for the path.
        """
        try:
            solver = z3_module.Solver()
            solver.set("timeout", 1000)  # 1s for model generation

            for cond in path.z3_conditions:
                solver.add(cond)

            result = solver.check()

            if result == z3_module.sat:
                model = solver.model()
                inputs = {}
                for var_name, z3_var in self._z3_vars.items():
                    val = model.eval(z3_var, model_completion=True)
                    try:
                        if z3_var.sort() == z3_module.IntSort():
                            inputs[var_name] = val.as_long()
                        elif z3_var.sort() == z3_module.BoolSort():
                            inputs[var_name] = bool(val)
                        elif z3_var.sort() == z3_module.RealSort():
                            dec_str = val.as_decimal(6)
                            inputs[var_name] = float(dec_str.rstrip('0').rstrip('.') if '.' in dec_str else dec_str)
                        else:
                            inputs[var_name] = str(val)
                    except Exception as e:
                        inputs[var_name] = str(val)
                        logger.debug("SymbolicExecutor: Z3 model value extraction failed for '%s': %s", var_name, e)
                smt_lib = solver.to_smt2()

                return {
                    "inputs": inputs,
                    "model_str": str(model),
                    "smt_lib": smt_lib,
                    "feasible": True,
                    "proven_with": "Z3_SMT",
                }
            elif result == z3_module.unsat:
                return {
                    "inputs": {},
                    "model_str": "UNSAT",
                    "smt_lib": "",
                    "feasible": False,
                    "proven_with": "Z3_SMT",
                }
            else:
                # Timeout or unknown
                return {
                    "inputs": {},
                    "model_str": "UNKNOWN/TIMEOUT",
                    "smt_lib": "",
                    "feasible": None,  # Unknown
                    "proven_with": "Z3_SMT",
                }

        except Exception as e:
            logger.debug("Z3 concrete input generation error: %s", e)
            return {
                "inputs": {},
                "model_str": f"ERROR: {e}",
                "smt_lib": "",
                "feasible": None,
                "proven_with": "Z3_SMT_ERROR",
            }

    def _generate_heuristic_inputs(self, path):
        """
        Fallback: generate approximate inputs from string-based path conditions.

        When Z3 is not available, attempts to extract constraints from the
        string representation of path conditions and produce heuristic inputs.
        """
        inputs = {}
        import re as _re

        for cond in path.condition:
            cond_str = str(cond)
            # Try to extract variable assignments from conditions
            # Pattern: SYM(var) == value
            eq_match = _re.match(r'SYM\((\w+)\)\s*==\s*(\d+)', cond_str)
            if eq_match:
                var_name, value = eq_match.group(1), int(eq_match.group(2))
                inputs[var_name] = value
                continue

            # Pattern: SYM(var) > value
            gt_match = _re.match(r'SYM\((\w+)\)\s*>\s*(\d+)', cond_str)
            if gt_match:
                var_name, value = gt_match.group(1), int(gt_match.group(2))
                inputs[var_name] = value + 1
                continue

            # Pattern: SYM(var) < value
            lt_match = _re.match(r'SYM\((\w+)\)\s*<\s*(\d+)', cond_str)
            if lt_match:
                var_name, value = lt_match.group(1), int(lt_match.group(2))
                inputs[var_name] = value - 1
                continue

            # Pattern: SYM(var) != value
            neq_match = _re.match(r'SYM\((\w+)\)\s*!=\s*(\d+)', cond_str)
            if neq_match:
                var_name, value = neq_match.group(1), int(neq_match.group(2))
                inputs[var_name] = value + 1

        # For variables referenced but not constrained, use default values
        for var_name in path.variables:
            if var_name not in inputs:
                sym_val = path.variables.get(var_name)
                if isinstance(sym_val, SymbolicValue) and sym_val.concrete is not None:
                    inputs[var_name] = sym_val.concrete
                else:
                    inputs[var_name] = 0  # Default concrete value

        return {
            "inputs": inputs,
            "model_str": str(inputs),
            "smt_lib": "",
            "feasible": True,  # Assumed feasible
            "proven_with": "STRING_HEURISTIC",
        }

    def prove_violation_reachable(self, violation, path):
        """
        Use Z3 to formally prove that a detected violation is reachable.

        Given a violation (e.g., "division by zero on var x") and the
        SymbolicPath where it was detected, constructs a Z3 query that
        checks: can the program reach a state where the violation occurs?

        Returns:
            dict with:
                - 'reachable': bool (True if Z3 proves the violation is reachable)
                - 'counterexample': dict of concrete values that trigger the violation
                - 'proof_method': 'Z3_FORMAL' or 'HEURISTIC'
        """
        if not HAS_Z3 or not path.z3_conditions:
            return {
                "reachable": True,  # Assume reachable without Z3
                "counterexample": {},
                "proof_method": "HEURISTIC",
                "note": "Z3 not available - assuming violation is reachable",
            }

        try:
            solver = z3_module.Solver()
            solver.set("timeout", 1000)

            # Add all path conditions (the path to the violation point)
            for cond in path.z3_conditions:
                solver.add(cond)

            # Add the violation condition
            violation_cond = self._violation_to_z3_condition(violation, path)
            if violation_cond is not None:
                solver.add(violation_cond)
            else:
                # Can't encode the violation in Z3 - assume reachable
                return {
                    "reachable": True,
                    "counterexample": {},
                    "proof_method": "HEURISTIC",
                    "note": "Violation could not be encoded in Z3",
                }

            result = solver.check()

            if result == z3_module.sat:
                # Z3 found a concrete input that reaches the violation!
                model = solver.model()
                counterexample = {}
                for var_name, z3_var in self._z3_vars.items():
                    val = model.eval(z3_var, model_completion=True)
                    try:
                        if z3_var.sort() == z3_module.IntSort():
                            counterexample[var_name] = val.as_long()
                        elif z3_var.sort() == z3_module.BoolSort():
                            counterexample[var_name] = bool(val)
                        else:
                            counterexample[var_name] = str(val)
                    except Exception as e:
                        counterexample[var_name] = str(val)
                        logger.debug("SymbolicExecutor: Z3 counterexample value extraction failed for '%s': %s", var_name, e)

                return {
                    "reachable": True,
                    "counterexample": counterexample,
                    "proof_method": "Z3_FORMAL",
                    "note": f"Z3 proved violation is reachable with inputs: {counterexample}",
                }
            elif result == z3_module.unsat:
                # Z3 proved the violation is NOT reachable under these path conditions
                return {
                    "reachable": False,
                    "counterexample": {},
                    "proof_method": "Z3_FORMAL",
                    "note": "Z3 proved violation is unreachable (path conditions prevent it)",
                }
            else:
                return {
                    "reachable": None,  # Unknown
                    "counterexample": {},
                    "proof_method": "Z3_FORMAL",
                    "note": "Z3 returned unknown/timeout - reachability undetermined",
                }

        except Exception as e:
            logger.debug("Z3 violation reachability proof error: %s", e)
            return {
                "reachable": True,
                "counterexample": {},
                "proof_method": "HEURISTIC",
                "note": f"Z3 error: {e}",
            }

    def _violation_to_z3_condition(self, violation, path):
        """
        Convert a violation string to a Z3 constraint that encodes
        the violation condition.

        Supported violation types:
        - "division by zero" on var X -> z3_var == 0
        - "None dereference" on var X -> z3_var == 0 (0 encodes None)
        - "index out of bounds" on var X -> z3_var < 0
        """
        import re as _re

        # Extract variable name from violation string
        var_match = _re.search(r"'(\w+)'", violation)
        if not var_match:
            return None

        var_name = var_match.group(1)
        z3_var = self._get_or_create_z3_var(var_name, "int")
        if z3_var is None:
            return None

        if "division by zero" in violation.lower():
            return z3_var == 0
        elif "none dereference" in violation.lower():
            return z3_var == 0
        elif "index out of bounds" in violation.lower() or "negative" in violation.lower():
            return z3_var < 0
        elif "type mismatch" in violation.lower():
            # Can't easily encode type violations as Z3 constraints
            return None

        return None

    def export_path_conditions_smt(self, paths, func_name=""):
        """
        Export all path conditions as SMT-LIB2 formulas for external analysis.

        This enables:
        - Offline verification with other SMT solvers
        - Integration with verification pipelines
        - Human-readable proof artifacts

        Returns:
            list of dicts, each with:
                - 'path_index': int
                - 'conditions': list of string conditions
                - 'smt_lib': SMT-LIB2 formula string (if Z3 available)
                - 'feasible': bool
                - 'concrete_inputs': dict of test inputs (if Z3 available)
        """
        exported = []

        for i, path in enumerate(paths):
            entry = {
                "path_index": i,
                "function": func_name,
                "conditions": [str(c) for c in path.condition],
                "feasible": path.is_feasible(),
                "is_pruned": path.is_pruned,
                "assignments": [(name, str(desc)) for name, desc in path.assignments],
                "return_values": path.return_values,
                "smt_lib": "",
                "concrete_inputs": {},
            }

            if HAS_Z3 and path.z3_conditions:
                try:
                    solver = z3_module.Solver()
                    solver.set("timeout", 500)
                    for cond in path.z3_conditions:
                        solver.add(cond)
                    entry["smt_lib"] = solver.to_smt2()

                    # Try to generate concrete test inputs
                    if solver.check() == z3_module.sat:
                        model = solver.model()
                        for var_name, z3_var in self._z3_vars.items():
                            val = model.eval(z3_var, model_completion=True)
                            try:
                                if z3_var.sort() == z3_module.IntSort():
                                    entry["concrete_inputs"][var_name] = val.as_long()
                                else:
                                    entry["concrete_inputs"][var_name] = str(val)
                            except Exception as e:
                                entry["concrete_inputs"][var_name] = str(val)
                                logger.debug("SymbolicExecutor: Path export value extraction failed for '%s': %s", var_name, e)
                except Exception as export_err:
                    logger.debug(f"SymbolicExecutor: Path export failed: {export_err}")

            exported.append(entry)

        return exported
