"""
ZENIC-AGENTS - Data Transform Block

Data transformation block: map, filter, aggregate, pivot, identity.
Extracted from data.py to keep file sizes under 400 lines.
"""

import re
import ast
import logging
from typing import Any, Dict

from .chain import LogicBlock

logger = logging.getLogger(__name__)


# ============================================================
#  DATA TRANSFORM BLOCK
# ============================================================


class DataTransformBlock(LogicBlock):
    """Transforma datos: map, filter, aggregate."""

    name = "data_transform"
    category = "data"
    description = "Map, filter, and aggregate data transformations"
    inputs = ["data", "transform_type", "config"]
    outputs = ["transformed_data", "metadata"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            source_data = data.get("data", data.get("items", []))
            transform_type = data.get("transform_type", "identity")  # map, filter, aggregate, pivot, identity
            config = data.get("config", {})

            if not isinstance(source_data, list):
                source_data = [source_data]

            result_data = source_data
            metadata = {"input_count": len(source_data), "transform_type": transform_type}

            if transform_type == "map":
                field_map = config.get("field_map", {})
                rename_map = config.get("rename", {})
                include_fields = config.get("include_fields", None)
                result_data = []
                for item in source_data:
                    if isinstance(item, dict):
                        mapped = {}
                        for k, v in item.items():
                            new_key = rename_map.get(k, k)
                            if include_fields is None or k in include_fields:
                                mapped[new_key] = v
                        # Apply computed fields (safe evaluation instead of eval())
                        for target_field, expression in field_map.items():
                            try:
                                # SECURITY FIX: Replace eval() with safe expression evaluation
                                # Only supports simple arithmetic and item field access
                                mapped[target_field] = self._safe_eval_expression(expression, item)
                            except Exception:
                                mapped[target_field] = None
                        result_data.append(mapped)

            elif transform_type == "filter":
                field_name = config.get("field", "")
                operator = config.get("operator", "==")
                value = config.get("value", None)
                result_data = [
                    item for item in source_data
                    if isinstance(item, dict) and self._compare(item.get(field_name), operator, value)
                ]

            elif transform_type == "aggregate":
                group_by = config.get("group_by", "")
                agg_field = config.get("field", "")
                agg_fn = config.get("function", "sum")  # sum, avg, count, min, max
                groups = {}
                for item in source_data:
                    if isinstance(item, dict):
                        key = item.get(group_by, "all")
                        groups.setdefault(key, [])
                        val = item.get(agg_field, 0)
                        if isinstance(val, (int, float)):
                            groups[key].append(val)
                result_data = []
                for key, values in groups.items():
                    agg_result = self._aggregate(values, agg_fn)
                    result_data.append({group_by: key, f"{agg_field}_{agg_fn}": agg_result, "count": len(values)})

            elif transform_type == "pivot":
                # Simple pivot: group by one field, aggregate another
                pivot_field = config.get("pivot_field", "")
                value_field = config.get("value_field", "")
                row_field = config.get("row_field", "")
                pivot_data = {}
                for item in source_data:
                    if isinstance(item, dict):
                        row_key = item.get(row_field, "unknown")
                        col_key = item.get(pivot_field, "unknown")
                        val = item.get(value_field, 0)
                        pivot_data.setdefault(row_key, {})[col_key] = val
                result_data = [{row_field: k, **v} for k, v in pivot_data.items()]

            metadata["output_count"] = len(result_data)
            logger.debug(f"DataTransformBlock: {transform_type}, {len(source_data)} -> {len(result_data)}")
            return {
                "success": True,
                "transformed_data": result_data,
                "metadata": metadata,
            }
        except Exception as e:
            return {"success": False, "error": f"DataTransformBlock: {str(e)}"}

    @staticmethod
    def _compare(actual, operator: str, expected) -> bool:
        """Compara valores con operador dado."""
        try:
            if operator == "==":
                return actual == expected
            elif operator == "!=":
                return actual != expected
            elif operator == ">":
                return actual > expected
            elif operator == "<":
                return actual < expected
            elif operator == ">=":
                return actual >= expected
            elif operator == "<=":
                return actual <= expected
            elif operator == "in":
                return actual in expected if expected else False
            elif operator == "contains":
                return expected in actual if actual else False
            elif operator == "not_null":
                return actual is not None
        except (TypeError, ValueError):
            return False
        return False

    @staticmethod
    def _safe_eval_expression(expression: str, item: Dict[str, Any]) -> Any:
        """
        SECURITY FIX: Reemplaza eval() con evaluación segura de expresiones.

        Solo soporta:
        - Acceso a campos del item: {field_name}
        - Aritmética simple: +, -, *, /
        - Funciones seguras: len(), str(), int(), float(), round()
        - Literales numéricos y strings

        NO soporta:
        - Importaciones, definiciones de funciones
        - Acceso a atributos con puntos (excepto los de item)
        - Cualquier código arbitrario
        """
        import re as _re

        if not expression or not isinstance(expression, str):
            return None

        expr = expression.strip()

        # Pattern 1: Simple field reference — "{field_name}" or just "field_name"
        if _re.match(r'^[a-zA-Z_]\w*$', expr):
            return item.get(expr)

        # Pattern 2: Field reference with braces — "{field_name}"
        brace_match = _re.match(r'^\{([a-zA-Z_]\w*)\}$', expr)
        if brace_match:
            return item.get(brace_match.group(1))

        # Pattern 3: Simple arithmetic — "field * 0.16" or "field1 + field2"
        # Allowed: field names, numbers, +, -, *, /, (, ), spaces
        # SECURITY: Replaced eval() with safe AST-based expression parser
        if _re.match(r'^[a-zA-Z_\d\s\+\-\*/\(\)\.\,]+$', expr):
            try:
                result = DataTransformBlock._safe_eval_arithmetic(expr, item, _re)
                if result is not None:
                    return result
            except Exception:
                pass

        # Pattern 4: Function call — "len(field)", "str(field)", etc.
        safe_funcs = {
            "len": lambda x: len(x) if x else 0,
            "str": str,
            "int": lambda x: int(x) if x else 0,
            "float": lambda x: float(x) if x else 0.0,
            "round": round,
            "abs": abs,
            "min": min,
            "max": max,
            "upper": lambda x: str(x).upper(),
            "lower": lambda x: str(x).lower(),
            "strip": lambda x: str(x).strip(),
        }
        func_match = _re.match(r'^(\w+)\(([^)]*)\)$', expr)
        if func_match:
            func_name = func_match.group(1)
            func_args_str = func_match.group(2).strip()
            if func_name in safe_funcs:
                # Parse arguments
                args = []
                for arg in func_args_str.split(','):
                    arg = arg.strip()
                    if _re.match(r'^[a-zA-Z_]\w*$', arg):
                        args.append(item.get(arg, arg))
                    elif arg.startswith('"') or arg.startswith("'"):
                        args.append(arg.strip('"\''))
                    else:
                        try:
                            args.append(float(arg) if '.' in arg else int(arg))
                        except ValueError:
                            args.append(arg)
                try:
                    return safe_funcs[func_name](*args)
                except Exception:
                    pass

        # Pattern 5: Conditional — "field if condition else default"
        # Not supported safely — return None
        return None

    @staticmethod
    def _safe_eval_arithmetic(expr: str, item: Dict[str, Any], _re) -> Any:
        """
        SECURITY: Evaluador aritmético seguro basado en AST.

        Reemplaza eval() con análisis sintáctico del árbol AST de Python.
        Solo permite: operaciones BinOp (+, -, *, /), Num/Constant, y
        nombres de campos del item que se resuelven a valores numéricos.

        Cualquier nodo AST no permitido causa que la expresión retorne None.
        """
        import ast as _ast

        # Primero, reemplazar nombres de campos con sus valores numéricos
        safe_expr = expr
        for field_name in sorted(item.keys(), key=len, reverse=True):
            if _re.match(r'^[a-zA-Z_]\w*$', field_name):
                value = item.get(field_name, 0)
                if isinstance(value, (int, float)):
                    safe_expr = safe_expr.replace(field_name, str(value))
                else:
                    safe_expr = safe_expr.replace(field_name, repr(str(value)))

        # Validar que solo queden números, operadores y paréntesis
        if not _re.match(r'^[\d\s\+\-\*/\(\)\.\'\"]+$', safe_expr):
            return None

        try:
            tree = _ast.parse(safe_expr, mode='eval')
        except SyntaxError:
            return None

        # Definir los nodos AST permitidos
        allowed_nodes = (
            _ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Num, _ast.Constant,
            _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.USub, _ast.UAdd,
        )

        # Verificar que todos los nodos del árbol sean seguros
        for node in _ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                return None

        # Evaluar el árbol AST de forma segura
        def _eval_node(node):
            if isinstance(node, _ast.Constant):
                return node.value
            if isinstance(node, _ast.Num):  # Python < 3.8 compat
                return node.n
            if isinstance(node, _ast.UnaryOp):
                operand = _eval_node(node.operand)
                if isinstance(node.op, _ast.USub):
                    return -operand
                if isinstance(node.op, _ast.UAdd):
                    return +operand
            if isinstance(node, _ast.BinOp):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                if isinstance(node.op, _ast.Add):
                    return left + right
                if isinstance(node.op, _ast.Sub):
                    return left - right
                if isinstance(node.op, _ast.Mult):
                    return left * right
                if isinstance(node.op, _ast.Div):
                    return left / right if right != 0 else 0
            return None

        return _eval_node(tree.body)

    @staticmethod
    def _aggregate(values: list, function: str):
        """Aplica funcion de agregacion."""
        if not values:
            return 0
        if function == "sum":
            return round(sum(values), 2)
        elif function == "avg":
            return round(sum(values) / len(values), 2)
        elif function == "count":
            return len(values)
        elif function == "min":
            return min(values)
        elif function == "max":
            return max(values)
        return sum(values)
