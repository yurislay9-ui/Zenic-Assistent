"""
ZENIC-AGENTS - Statement Processors Mixin

Simple statement processing methods for the SymbolicExecutor:
- _process_assign: Handle ast.Assign
- _process_aug_assign: Handle ast.AugAssign
- _process_return: Handle ast.Return
- _process_if: Handle ast.If (path forking)

Loop and compound processors (for, while, try, expr_stmt) are in statement_loops.py.

This module provides a mixin class that is composed into SymbolicExecutor.
"""

import ast
import logging

logger = logging.getLogger(__name__)

from ..z3_solver import HAS_Z3

# Z3 module reference for convenience (only available when HAS_Z3 is True)
if HAS_Z3:
    import z3 as z3_module  # type: ignore[import-unresolved]

from .types import SymbolicValue, SymbolicPath


class StatementProcessorMixin:
    """
    Mixin for SymbolicExecutor providing simple statement processing methods.
    """

    # ----------------------------------------------------------------
    #  Statement Processors
    # ----------------------------------------------------------------

    def _process_assign(self, stmt, path):
        """Process ast.Assign: update symbolic state with new value."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        for target in stmt.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                sym_val = self._eval_assign_value(stmt.value, new_path, var_name)
                new_path.variables[var_name] = sym_val
                new_path.add_assignment(var_name, self._symbolize_expr(stmt.value, path))

                # Update Z3 var if we have a concrete value
                if HAS_Z3 and sym_val.concrete is not None:
                    z3_var = self._get_or_create_z3_var(var_name)
                    if z3_var is not None and len(new_path.z3_conditions) < SymbolicPath.MAX_Z3_CONDITIONS:
                        if isinstance(sym_val.concrete, int):
                            new_path.z3_conditions.append(z3_var == sym_val.concrete)

            elif isinstance(target, ast.Tuple) or isinstance(target, ast.List):
                # Tuple/list unpacking: simplified handling
                for i, elt in enumerate(target.elts):
                    if isinstance(elt, ast.Name):
                        var_name = elt.id
                        sym_val = SymbolicValue(
                            name=var_name,
                            var_type="any",
                            constraint=None
                        )
                        new_path.variables[var_name] = sym_val
                        new_path.add_assignment(var_name, f"unpack[{i}]")

            elif isinstance(target, ast.Subscript):
                # x[key] = value: simplified - mark x as modified
                if isinstance(target.value, ast.Name):
                    var_name = target.value.id
                    if var_name in new_path.variables:
                        # Mark as possibly modified
                        existing = new_path.variables[var_name]
                        new_path.variables[var_name] = SymbolicValue(
                            name=var_name,
                            var_type=existing.var_type,
                            constraint=existing.constraint,
                            concrete=None  # No longer concretely known
                        )
                        new_path.add_assignment(f"{var_name}[...]", self._symbolize_expr(stmt.value, path))

        return new_path

    def _process_aug_assign(self, stmt, path):
        """Process ast.AugAssign (x += 1, x -= 2, etc.)."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        if isinstance(stmt.target, ast.Name):
            var_name = stmt.target.id
            old_val = new_path.variables.get(var_name)
            old_type = old_val.var_type if old_val else "any"

            # Compute new concrete value if possible
            new_concrete = None
            if old_val and old_val.concrete is not None:
                rhs_concrete = self._try_eval_concrete(stmt.value, new_path)
                if rhs_concrete is not None:
                    op_map = {
                        ast.Add: lambda a, b: a + b,
                        ast.Sub: lambda a, b: a - b,
                        ast.Mult: lambda a, b: a * b,
                        ast.Mod: lambda a, b: a % b if b != 0 else None,
                        ast.FloorDiv: lambda a, b: a // b if b != 0 else None,
                    }
                    op_fn = op_map.get(type(stmt.op))
                    if op_fn:
                        try:
                            new_concrete = op_fn(old_val.concrete, rhs_concrete)
                        except (TypeError, ZeroDivisionError):
                            new_concrete = None

            op_str_map = {
                ast.Add: "+=", ast.Sub: "-=", ast.Mult: "*=",
                ast.Div: "/=", ast.Mod: "%=", ast.FloorDiv: "//=",
            }
            op_str = op_str_map.get(type(stmt.op), "?=")
            rhs_str = self._symbolize_expr(stmt.value, path)

            new_path.variables[var_name] = SymbolicValue(
                name=var_name,
                var_type=old_type,
                concrete=new_concrete
            )
            new_path.add_assignment(var_name, f"{var_name}{op_str}{rhs_str}")

            # Z3: add constraint for the augmented assignment
            if HAS_Z3 and new_concrete is not None:
                z3_var = self._get_or_create_z3_var(var_name)
                if z3_var is not None and len(new_path.z3_conditions) < SymbolicPath.MAX_Z3_CONDITIONS:
                    new_path.z3_conditions.append(z3_var == new_concrete)

        return new_path

    def _process_return(self, stmt, path):
        """Process ast.Return: track return value and end the path."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        if stmt.value is not None:
            ret_desc = self._symbolize_expr(stmt.value, path)
            ret_type = "any"
            ret_concrete = self._try_eval_concrete(stmt.value, path)

            # Infer return type from expression
            if isinstance(stmt.value, ast.Constant):
                if stmt.value.value is None:
                    ret_type = "None"
                elif isinstance(stmt.value.value, bool):
                    ret_type = "bool"
                elif isinstance(stmt.value.value, int):
                    ret_type = "int"
                elif isinstance(stmt.value.value, float):
                    ret_type = "float"
                elif isinstance(stmt.value.value, str):
                    ret_type = "str"
            elif isinstance(stmt.value, ast.Name):
                if stmt.value.id in path.variables:
                    ret_type = path.variables[stmt.value.id].var_type
            elif isinstance(stmt.value, (ast.List, ast.ListComp)):
                ret_type = "list"
            elif isinstance(stmt.value, (ast.Dict, ast.DictComp)):
                ret_type = "dict"
            elif isinstance(stmt.value, ast.Call):
                func_name = self._get_call_name(stmt.value)
                # Try to infer from known function return types
                if func_name == "len":
                    ret_type = "int"
                elif func_name == "str":
                    ret_type = "str"
                elif func_name == "int":
                    ret_type = "int"
                elif func_name == "float":
                    ret_type = "float"
                elif func_name == "list":
                    ret_type = "list"
                elif func_name == "dict":
                    ret_type = "dict"
                elif func_name == "bool":
                    ret_type = "bool"

            new_path.add_return(ret_desc, ret_type)
            new_path.result = ret_desc
        else:
            # bare return -> returns None
            new_path.add_return("None", "None")
            new_path.result = "None"

        return new_path

    def _process_if(self, stmt, path):
        """Process ast.If: fork path into true and false branches."""
        true_str, true_z3 = self._encode_z3_condition(stmt.test, path, negate=False)
        false_str = f"NOT_{true_str}"
        false_z3 = None
        if HAS_Z3 and true_z3 is not None:
            try:
                false_z3 = z3_module.Not(true_z3)
            except Exception as e:
                false_z3 = None
                logger.debug("SymbolicExecutor: Z3 Not() negation failed: %s", e)

        # True branch
        true_path = SymbolicPath(
            condition=path.condition + [true_str],
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        if true_z3 is not None:
            true_path.add_condition(true_str, true_z3)
        else:
            true_path.add_condition(true_str)

        # Process true body statements
        true_paths = self._process_stmts(stmt.body, true_path)

        # False branch
        false_path = SymbolicPath(
            condition=path.condition + [false_str],
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        if false_z3 is not None:
            false_path.add_condition(false_str, false_z3)
        else:
            false_path.add_condition(false_str)

        if stmt.orelse:
            false_paths = self._process_stmts(stmt.orelse, false_path)
        else:
            false_paths = [false_path]

        # Check I/O in branches
        for i in range(len(true_paths)):
            true_paths[i] = self._check_io_in_body(stmt.body, true_paths[i])
        for i in range(len(false_paths)):
            if stmt.orelse:
                false_paths[i] = self._check_io_in_body(stmt.orelse, false_paths[i])

        return true_paths + false_paths
