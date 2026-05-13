"""
ZENIC-AGENTS - Violation Detection Mixin

Violation detection methods for the SymbolicExecutor:
- _check_path_violations: Main dispatcher for violation checks
- _check_none_dereference: None dereference detection
- _check_division_by_zero: Division by zero detection
- _check_index_out_of_bounds: Index out of bounds detection
- _check_type_mismatches: Type mismatch detection
- _check_uninitialized_variables: Uninitialized variable detection
- _check_return_consistency: Return consistency checking

This module provides a mixin class that is composed into SymbolicExecutor.
"""

import ast
import logging

logger = logging.getLogger(__name__)

from ..z3_solver import HAS_Z3

# Z3 module reference for convenience (only available when HAS_Z3 is True)
if HAS_Z3:
    import z3 as z3_module

from .types import SymbolicValue


class ViolationCheckerMixin:
    """
    Mixin for SymbolicExecutor providing violation detection methods.
    """

    # ----------------------------------------------------------------
    #  Violation Detection
    # ----------------------------------------------------------------

    def _check_path_violations(self, path, func_name):
        """
        Verifica violaciones de invariantes en un camino simbolico.

        Detecta:
        - None dereference
        - Division by zero
        - Index out of bounds
        - Type mismatches
        - Uninitialized variable usage
        """
        violations = []

        # 1. Verificar None dereference
        self._check_none_dereference(path, func_name, violations)

        # 2. Verificar division by zero
        self._check_division_by_zero(path, func_name, violations)

        # 3. Verificar index out of bounds
        self._check_index_out_of_bounds(path, func_name, violations)

        # 4. Verificar type mismatches
        self._check_type_mismatches(path, func_name, violations)

        # 5. Verificar uninitialized variable usage
        self._check_uninitialized_variables(path, func_name, violations)

        return violations

    def _check_none_dereference(self, path, func_name, violations):
        """Check for potential None dereference on a path."""
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue):
                if sym_val.var_type == "None":
                    # Variable may be None - check if path condition excludes it
                    for cond in path.condition:
                        cond_str = str(cond)
                        if (f"SYM({var_name})!=" in cond_str or
                                f"SYM({var_name}) is_not None" in cond_str or
                                f"SYM({var_name}) is_not None" in cond_str):
                            break
                    else:
                        violations.append(
                            f"Potential None dereference: '{var_name}' may be None "
                            f"in function '{func_name}'"
                        )

    def _check_division_by_zero(self, path, func_name, violations):
        """Check for potential division by zero on a path."""
        # Collect all expression descriptions (from assignments and return values)
        all_exprs = [str(desc) for _, desc in path.assignments]
        for rv in path.return_values:
            all_exprs.append(str(rv.get("desc", "")))

        # Check 1: variables with known concrete value of 0 used as denominator
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue) and sym_val.concrete == 0:
                # Check if this variable is used as a denominator in any expression
                for expr_str in all_exprs:
                    if f"/SYM({var_name})" in expr_str or f"%SYM({var_name})" in expr_str:
                        violations.append(
                            f"Potential division by zero: '{var_name}' may be 0 "
                            f"in function '{func_name}'"
                        )
                        break  # One violation per variable is enough

        # Check 2: scan all expression descriptions for division patterns
        # and check if denominator variable can be 0 using Z3 or heuristic
        import re as _re
        for expr_str in all_exprs:
            # Find all denominator variables in division/modulo operations
            # Match patterns like /SYM(var) or %SYM(var)
            denom_refs = _re.findall(r'[/%]SYM\((\w+)\)', expr_str)
            for denom_var in denom_refs:
                sym_val = path.variables.get(denom_var)
                if not isinstance(sym_val, SymbolicValue):
                    continue
                # If the variable is known to be None, skip (that's a None deref)
                if sym_val.var_type == "None":
                    continue
                # If we already detected this variable, skip
                already_found = any(
                    f"'{denom_var}'" in v for v in violations
                )
                if already_found:
                    continue
                # If concrete value is known and non-zero, it's safe
                if sym_val.concrete is not None and sym_val.concrete != 0:
                    continue
                # Use Z3 to check if the variable can be 0 on this path
                if HAS_Z3:
                    try:
                        z3_var = self._get_or_create_z3_var(denom_var, "int")
                        if z3_var is not None:
                            test_solver = z3_module.Solver()
                            test_solver.set("timeout", 300)
                            # Add all existing path conditions
                            for cond in path.z3_conditions:
                                test_solver.add(cond)
                            # Check: can the denominator be 0?
                            test_solver.add(z3_var == 0)
                            if test_solver.check() == z3_module.sat:
                                violations.append(
                                    f"Potential division by zero: '{denom_var}' can be 0 "
                                    f"in function '{func_name}' (Z3 verified)"
                                )
                            # else: Z3 proved it can't be zero - safe
                    except Exception as e:
                        # Z3 failed - use heuristic: if variable is not constrained
                        # away from zero, flag it as potential issue
                        logger.debug("SymbolicExecutor: Z3 div-by-zero check failed: %s", e)
                        is_constrained_nonzero = any(
                            f"SYM({denom_var})!=0" in str(c) or
                            f"SYM({denom_var})>0" in str(c) or
                            f"SYM({denom_var})<" in str(c)
                            for c in path.condition
                        )
                        if not is_constrained_nonzero:
                            violations.append(
                                f"Potential division by zero: '{denom_var}' may be 0 "
                                f"in function '{func_name}'"
                            )
                else:
                    # No Z3: heuristic check - is the variable constrained away from zero?
                    is_constrained_nonzero = any(
                        f"SYM({denom_var})!=0" in str(c) or
                        f"SYM({denom_var})>0" in str(c) or
                        f"SYM({denom_var})<" in str(c)
                        for c in path.condition
                    )
                    if not is_constrained_nonzero and sym_val.concrete is None:
                        violations.append(
                            f"Potential division by zero: '{denom_var}' may be 0 "
                            f"in function '{func_name}'"
                        )

    def _check_index_out_of_bounds(self, path, func_name, violations):
        """Check for potential index out of bounds access."""
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue) and sym_val.var_type == "int":
                # Check if this int variable is used as an index
                for _, desc in path.assignments:
                    desc_str = str(desc)
                    # Pattern: something[var_name] - using var as index
                    if f"[{var_name}]" in desc_str or f"[SYM({var_name})]" in desc_str:
                        # Check if the index can be negative or too large
                        if sym_val.concrete is not None:
                            if sym_val.concrete < 0:
                                violations.append(
                                    f"Potential index out of bounds: '{var_name}' = {sym_val.concrete} "
                                    f"(negative index) in function '{func_name}'"
                                )
                        else:
                            # Variable is symbolic - check with Z3 if it can be negative
                            if HAS_Z3 and path.z3_conditions:
                                try:
                                    z3_var = self._get_or_create_z3_var(var_name, "int")
                                    if z3_var is not None:
                                        test_solver = z3_module.Solver()
                                        test_solver.set("timeout", 300)
                                        for cond in path.z3_conditions:
                                            test_solver.add(cond)
                                        test_solver.add(z3_var < 0)
                                        if test_solver.check() == z3_module.sat:
                                            violations.append(
                                                f"Potential index out of bounds: '{var_name}' may be "
                                                f"negative in function '{func_name}' (Z3 verified)"
                                            )
                                except Exception as z3_err:
                                    logger.debug(f"SymbolicExecutor: Z3 bounds check failed: {z3_err}")

    def _check_type_mismatches(self, path, func_name, violations):
        """Check for type mismatches in binary operations."""
        # Collect all expression descriptions (from assignments and return values)
        import re as _re
        all_exprs = [str(desc) for _, desc in path.assignments]
        for rv in path.return_values:
            all_exprs.append(str(rv.get("desc", "")))

        # Check all expressions for pairs of variables with incompatible types
        checked_pairs = set()
        for expr_str in all_exprs:
            # Find all SYM(var) references in this expression
            sym_refs = _re.findall(r'SYM\((\w+)\)', expr_str)
            if len(sym_refs) < 2:
                continue
            # Check all pairs of referenced variables for type incompatibility
            for i in range(len(sym_refs)):
                for j in range(i + 1, len(sym_refs)):
                    v1_name = sym_refs[i]
                    v2_name = sym_refs[j]
                    pair_key = (v1_name, v2_name) if v1_name < v2_name else (v2_name, v1_name)
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)
                    v1 = path.variables.get(v1_name)
                    v2 = path.variables.get(v2_name)
                    if not isinstance(v1, SymbolicValue) or not isinstance(v2, SymbolicValue):
                        continue
                    t1 = v1.var_type
                    t2 = v2.var_type
                    if t1 != "any" and t2 != "any" and t1 != t2:
                        pair = frozenset({t1, t2})
                        if pair in self.INCOMPATIBLE_TYPES:
                            violations.append(
                                f"Potential type mismatch: '{v1_name}' ({t1}) and "
                                f"'{v2_name}' ({t2}) used together "
                                f"in function '{func_name}'"
                            )

    def _check_uninitialized_variables(self, path, func_name, violations):
        """Check for use of uninitialized variables on a path."""
        import re as _re

        # Build set of variables that are assigned on this path
        assigned_vars = set()
        for var_name, _ in path.assignments:
            assigned_vars.add(var_name)

        # Build set of function parameters (always initialized)
        param_vars = set()
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue) and var_name not in assigned_vars:
                param_vars.add(var_name)

        initialized = assigned_vars | param_vars

        # Check return value descriptions for bare variable names
        # A bare name (not inside SYM()) in a return expression means the variable
        # was NOT in the symbolic state when referenced = potentially uninitialized
        for rv in path.return_values:
            desc = str(rv.get("desc", ""))
            # If the description is just a bare name (not SYM(...), not a literal)
            # then the variable was not in the symbolic state when used
            if not desc.startswith("SYM(") and not desc.startswith(("'", '"', '-', '(')):
                # It's a bare name - check if it was initialized
                if (desc not in {'None', 'True', 'False', 'UNKNOWN', 'SYM_EXPR'}
                        and not desc[0].isdigit()
                        and desc not in path.variables
                        and desc not in initialized
                        and not desc.startswith('_')
                        and '(' not in desc):
                    violations.append(
                        f"Potential uninitialized variable: '{desc}' used "
                        f"in function '{func_name}'"
                    )

    # ----------------------------------------------------------------
    #  Return Consistency Check
    # ----------------------------------------------------------------

    def _check_return_consistency(self, paths, func_name):
        """Check if all paths return a value and return types are consistent."""
        warnings = []

        # Check for paths that don't return (fall off the end)
        paths_without_return = []
        for path in paths:
            if not path.return_values:
                paths_without_return.append(path)

        if paths_without_return:
            warnings.append(
                f"Function '{func_name}' may not return a value on all paths "
                f"({len(paths_without_return)} path(s) fall off the end without returning)"
            )

        # Check return type consistency
        return_types = set()
        for path in paths:
            for rv in path.return_values:
                rt = rv.get("type", "any")
                if rt != "exception":  # Don't count raises as return types
                    return_types.add(rt)

        # If we have incompatible return types, warn
        non_any_types = return_types - {"any"}
        if len(non_any_types) > 1:
            # None is sometimes acceptable alongside other types (Optional)
            non_none_types = non_any_types - {"None"}
            if len(non_none_types) > 1:
                warnings.append(
                    f"Function '{func_name}' may return inconsistent types: {non_any_types}"
                )

        return warnings
