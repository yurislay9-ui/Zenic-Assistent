"""
ZENIC-AGENTS - Executor Helpers Mixin

Helper methods for the SymbolicExecutor:
- Value evaluation: _eval_assign_value, _try_eval_concrete, _annotation_to_type
- Symbolic expression helpers: _symbolize_condition, _symbolize_expr,
  _get_call_name, _check_io_in_body

This module provides a mixin class that is composed into SymbolicExecutor.
"""

import ast
import logging

logger = logging.getLogger(__name__)

from .types import SymbolicValue, SymbolicPath


class ExecutorHelpersMixin:
    """
    Mixin for SymbolicExecutor providing value evaluation and
    symbolic expression helper methods.
    """

    # ----------------------------------------------------------------
    #  Value Evaluation Helpers
    # ----------------------------------------------------------------

    def _eval_assign_value(self, value_node, path, var_name):
        """Evaluate the RHS of an assignment to create a SymbolicValue."""
        # Try to get a concrete value first
        concrete = self._try_eval_concrete(value_node, path)
        var_type = "any"

        if isinstance(value_node, ast.Constant):
            if value_node.value is None:
                var_type = "None"
            elif isinstance(value_node.value, bool):
                var_type = "bool"
            elif isinstance(value_node.value, int):
                var_type = "int"
            elif isinstance(value_node.value, float):
                var_type = "float"
            elif isinstance(value_node.value, str):
                var_type = "str"
        elif isinstance(value_node, (ast.List, ast.ListComp)):
            var_type = "list"
        elif isinstance(value_node, (ast.Dict, ast.DictComp)):
            var_type = "dict"
        elif isinstance(value_node, ast.Name):
            if value_node.id in path.variables:
                src = path.variables[value_node.id]
                var_type = src.var_type
                if concrete is None and src.concrete is not None:
                    concrete = src.concrete
        elif isinstance(value_node, ast.BinOp):
            # Infer type from operands
            left_type = "any"
            right_type = "any"
            if isinstance(value_node.left, ast.Name) and value_node.left.id in path.variables:
                left_type = path.variables[value_node.left.id].var_type
            if isinstance(value_node.right, ast.Name) and value_node.right.id in path.variables:
                right_type = path.variables[value_node.right.id].var_type
            if left_type in ("int", "float") and right_type in ("int", "float"):
                var_type = "float" if "float" in (left_type, right_type) else "int"
            elif left_type == "str" and right_type == "str" and isinstance(value_node.op, ast.Add):
                var_type = "str"
        elif isinstance(value_node, ast.Call):
            func_name = self._get_call_name(value_node)
            type_inference = {
                "int": "int", "float": "float", "str": "str",
                "bool": "bool", "list": "list", "dict": "dict",
                "len": "int", "range": "list", "type": "type",
            }
            var_type = type_inference.get(func_name, "any")
            # Check if calling a known function in our func_map
            if func_name in getattr(self, '_func_map', {}):
                var_type = "return_type_of_func"

        return SymbolicValue(
            name=var_name,
            var_type=var_type,
            concrete=concrete
        )

    def _try_eval_concrete(self, node, path):
        """Try to evaluate an AST node to a concrete Python value."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in path.variables:
                sym_val = path.variables[node.id]
                if isinstance(sym_val, SymbolicValue) and sym_val.concrete is not None:
                    return sym_val.concrete
        elif isinstance(node, ast.BinOp):
            left = self._try_eval_concrete(node.left, path)
            right = self._try_eval_concrete(node.right, path)
            if left is not None and right is not None:
                try:
                    if isinstance(node.op, ast.Add):
                        return left + right
                    elif isinstance(node.op, ast.Sub):
                        return left - right
                    elif isinstance(node.op, ast.Mult):
                        return left * right
                    elif isinstance(node.op, ast.Div):
                        return left / right if right != 0 else None
                    elif isinstance(node.op, ast.FloorDiv):
                        return left // right if right != 0 else None
                    elif isinstance(node.op, ast.Mod):
                        return left % right if right != 0 else None
                except (TypeError, ZeroDivisionError):
                    return None
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._try_eval_concrete(node.operand, path)
            if inner is not None:
                try:
                    return -inner
                except TypeError:
                    return None
        elif isinstance(node, ast.Call):
            func_name = self._get_call_name(node)
            if func_name == "len" and node.args:
                inner = self._try_eval_concrete(node.args[0], path)
                if inner is not None and hasattr(inner, '__len__'):
                    try:
                        return len(inner)
                    except TypeError:
                        return None
        return None

    def _annotation_to_type(self, annotation):
        """Convert a type annotation AST node to a type string."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Attribute):
            return annotation.attr
        return "any"

    # ----------------------------------------------------------------
    #  Symbolic Expression Helpers
    # ----------------------------------------------------------------

    def _symbolize_condition(self, test_node, current_path):
        """Convierte una condicion AST en una representacion simbolica."""
        if isinstance(test_node, ast.Compare):
            left = self._symbolize_expr(test_node.left, current_path)
            ops = {
                ast.Eq: "==", ast.NotEq: "!=",
                ast.Lt: "<", ast.LtE: "<=",
                ast.Gt: ">", ast.GtE: ">=",
                ast.Is: "is", ast.IsNot: "is_not",
            }
            right_parts = []
            for op, comp in zip(test_node.ops, test_node.comparators):
                op_str = ops.get(type(op), "?")
                right = self._symbolize_expr(comp, current_path)
                right_parts.append(f"{left}{op_str}{right}")
            return "_AND_".join(right_parts)

        elif isinstance(test_node, ast.BoolOp):
            if isinstance(test_node.op, ast.And):
                parts = [self._symbolize_expr(v, current_path) for v in test_node.values]
                return "_AND_".join(parts)
            elif isinstance(test_node.op, ast.Or):
                parts = [self._symbolize_expr(v, current_path) for v in test_node.values]
                return "_OR_".join(parts)

        elif isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not):
            inner = self._symbolize_expr(test_node.operand, current_path)
            return f"NOT_{inner}"

        elif isinstance(test_node, ast.Name):
            return f"TRUTHY_{test_node.id}"

        return "UNKNOWN_COND"

    def _symbolize_expr(self, node, current_path):
        """Convierte una expresion AST en representacion simbolica."""
        if isinstance(node, ast.Name):
            if node.id in current_path.variables:
                return f"SYM({node.id})"
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            value = self._symbolize_expr(node.value, current_path)
            return f"{value}.{node.attr}"
        elif isinstance(node, ast.Call):
            func_name = self._get_call_name(node)
            # Path Pruning: si es I/O, podar
            if func_name in self.IO_OPERATIONS:
                return f"MOCKED_IO({func_name})"
            args = [self._symbolize_expr(a, current_path) for a in node.args]
            return f"{func_name}({', '.join(args)})"
        elif isinstance(node, ast.BinOp):
            left = self._symbolize_expr(node.left, current_path)
            right = self._symbolize_expr(node.right, current_path)
            op_map = {
                ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
                ast.Mod: "%", ast.FloorDiv: "//",
            }
            op_str = op_map.get(type(node.op), "?")
            return f"({left}{op_str}{right})"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._symbolize_expr(node.operand, current_path)
            return f"-{inner}"
        elif isinstance(node, ast.Subscript):
            value = self._symbolize_expr(node.value, current_path)
            if isinstance(node.slice, ast.Index):  # Python 3.8 compat
                slice_expr = self._symbolize_expr(node.slice.value, current_path)
            else:
                slice_expr = self._symbolize_expr(node.slice, current_path)
            return f"{value}[{slice_expr}]"
        elif isinstance(node, (ast.List, ast.Tuple)):
            elts = [self._symbolize_expr(e, current_path) for e in node.elts]
            brackets = "[]" if isinstance(node, ast.List) else "()"
            return f"{brackets[0]}{', '.join(elts)}{brackets[1]}"
        return "SYM_EXPR"

    def _get_call_name(self, call_node):
        """Obtiene el nombre de una llamada a funcion."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            if isinstance(call_node.func.value, ast.Name):
                return f"{call_node.func.value.id}.{call_node.func.attr}"
            return call_node.func.attr
        return "unknown_call"

    def _check_io_in_body(self, body, path):
        """Verifica si un bloque contiene I/O y marca el camino como podado."""
        for node in ast.walk(ast.Module(body=body, type_ignores=[])):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                base_name = call_name.split('.')[-1] if '.' in call_name else call_name
                if base_name in self.IO_OPERATIONS:
                    path.is_pruned = True
                    # Mockear I/O: agregar variable simbolica
                    path.variables[f"_mocked_{call_name}"] = SymbolicValue(
                        name=f"_mocked_{call_name}",
                        var_type="mocked_io",
                        constraint=lambda x: True  # Asumimos resultado valido
                    )
                    break
        return path
