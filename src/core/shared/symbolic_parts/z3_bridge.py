"""
ZENIC-AGENTS - Z3 Bridge Mixin

Z3 variable management, constraint encoding, and feasibility methods
for the SymbolicExecutor. Also includes the _symbolic_regex fallback
for non-Python languages.

This module provides a mixin class that is composed into SymbolicExecutor.
"""

import ast
import logging

logger = logging.getLogger(__name__)

from ..z3_solver import HAS_Z3

# Z3 module reference for convenience (only available when HAS_Z3 is True)
if HAS_Z3:
    import z3 as z3_module  # type: ignore[import-unresolved]

from .types import SymbolicValue


class Z3BridgeMixin:
    """
    Mixin for SymbolicExecutor providing Z3 variable management,
    constraint encoding, and non-Python language fallback.
    """

    # ----------------------------------------------------------------
    #  Z3 Variable Management
    # ----------------------------------------------------------------

    def _get_or_create_z3_var(self, name, var_type="int"):
        """Get or create a Z3 variable for the given symbolic variable name."""
        if name in self._z3_vars:
            return self._z3_vars[name]
        if HAS_Z3:
            if var_type in ("int", "any"):
                z3_var = z3_module.Int(name)
            elif var_type == "bool":
                z3_var = z3_module.Bool(name)
            else:
                z3_var = z3_module.Int(name)  # Default to Int
            self._z3_vars[name] = z3_var
            return z3_var
        return None

    def _encode_z3_condition(self, test_node, current_path, negate=False):
        """
        Encode an AST condition as a Z3 constraint.

        Returns (string_condition, z3_constraint_or_None).
        """
        string_cond = self._symbolize_condition(test_node, current_path)
        z3_cond = None

        if HAS_Z3:
            try:
                z3_cond = self._build_z3_constraint(test_node, current_path, negate=negate)
            except Exception as e:
                z3_cond = None
                logger.debug("SymbolicExecutor: Z3 constraint encoding failed: %s", e)

        return string_cond, z3_cond

    def _build_z3_constraint(self, node, current_path, negate=False):
        """Build a Z3 constraint from an AST test node."""
        if not HAS_Z3:
            return None

        constraint = self._z3_expr_from_node(node, current_path)

        if constraint is None:
            return None

        if negate:
            constraint = z3_module.Not(constraint)
        return constraint

    def _z3_expr_from_node(self, node, current_path):
        """Recursively build a Z3 boolean expression from an AST node."""
        if not HAS_Z3:
            return None

        if isinstance(node, ast.Compare):
            left = self._z3_value_from_node(node.left, current_path)
            if left is None:
                return None
            z3_conds = []
            for op, comp in zip(node.ops, node.comparators):
                right = self._z3_value_from_node(comp, current_path)
                if right is None:
                    return None
                if isinstance(op, ast.Eq):
                    z3_conds.append(left == right)
                elif isinstance(op, ast.NotEq):
                    z3_conds.append(left != right)
                elif isinstance(op, ast.Lt):
                    z3_conds.append(left < right)
                elif isinstance(op, ast.LtE):
                    z3_conds.append(left <= right)
                elif isinstance(op, ast.Gt):
                    z3_conds.append(left > right)
                elif isinstance(op, ast.GtE):
                    z3_conds.append(left >= right)
                elif isinstance(op, ast.Is):
                    z3_conds.append(left == right)
                elif isinstance(op, ast.IsNot):
                    z3_conds.append(left != right)
                else:
                    return None
                left = right  # Chain comparisons
            if len(z3_conds) == 1:
                return z3_conds[0]
            return z3_module.And(*z3_conds)

        elif isinstance(node, ast.BoolOp):
            parts = []
            for v in node.values:
                part = self._z3_expr_from_node(v, current_path)
                if part is None:
                    return None
                parts.append(part)
            if isinstance(node.op, ast.And):
                return z3_module.And(*parts)
            elif isinstance(node.op, ast.Or):
                return z3_module.Or(*parts)

        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self._z3_expr_from_node(node.operand, current_path)
            if inner is None:
                return None
            return z3_module.Not(inner)

        elif isinstance(node, ast.Name):
            # TRUTHY check
            z3_var = self._get_or_create_z3_var(node.id)
            if z3_var is not None:
                return z3_var != 0

        return None

    def _z3_value_from_node(self, node, current_path):
        """Extract a Z3 numeric value from an AST expression node."""
        if not HAS_Z3:
            return None

        if isinstance(node, ast.Constant):
            if isinstance(node.value, int):
                return z3_module.IntVal(node.value)
            elif isinstance(node.value, bool):
                return z3_module.IntVal(1 if node.value else 0)
            elif node.value is None:
                return z3_module.IntVal(0)  # 0 = None in our encoding
        elif isinstance(node, ast.Name):
            if node.id in current_path.variables:
                sym_val = current_path.variables[node.id]
                if isinstance(sym_val, SymbolicValue) and sym_val.concrete is not None:
                    if isinstance(sym_val.concrete, int):
                        return z3_module.IntVal(sym_val.concrete)
                    elif sym_val.concrete is None:
                        return z3_module.IntVal(0)
            z3_var = self._get_or_create_z3_var(node.id)
            if z3_var is not None:
                return z3_var
        elif isinstance(node, ast.BinOp):
            left = self._z3_value_from_node(node.left, current_path)
            right = self._z3_value_from_node(node.right, current_path)
            if left is not None and right is not None:
                if isinstance(node.op, ast.Add):
                    return left + right
                elif isinstance(node.op, ast.Sub):
                    return left - right
                elif isinstance(node.op, ast.Mult):
                    return left * right
                elif isinstance(node.op, (ast.Div, ast.FloorDiv)):
                    return left  # Simplified - don't encode division in Z3 value
                elif isinstance(node.op, ast.Mod):
                    return left  # Simplified
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._z3_value_from_node(node.operand, current_path)
            if inner is not None:
                return -inner

        return None

    # ----------------------------------------------------------------
    #  Non-Python Language Fallback
    # ----------------------------------------------------------------

    def _symbolic_regex(self, code, language, target_name):
        """Analisis simbolico simplificado para lenguajes no-Python."""
        # Contar ramas condicionales
        branch_patterns = {
            "kotlin": r'\bif\b|\bwhen\b|\belse\b',
            "go": r'\bif\b|\bswitch\b|\belse\b',
            "javascript": r'\bif\b|\bswitch\b|\belse\b|\?.*:',
            "typescript": r'\bif\b|\bswitch\b|\belse\b|\?.*:',
            "java": r'\bif\b|\bswitch\b|\belse\b',
            "rust": r'\bif\b|\bmatch\b|\belse\b',
        }
        pattern = branch_patterns.get(language, r'\bif\b|\belse\b')
        import re
        branches = len(re.findall(pattern, code))
        estimated_paths = min(2 ** branches, 1000) if branches > 0 else 1

        return {
            "status": "PASS",
            "paths": [],
            "violations": [],
            "warnings": [f"Symbolic execution for {language} uses estimation ({estimated_paths} estimated paths)"],
            "metrics": {
                "paths_explored": estimated_paths,
                "paths_pruned": 0,
                "total_paths": estimated_paths,
                "feasible_paths": estimated_paths,
            }
        }
