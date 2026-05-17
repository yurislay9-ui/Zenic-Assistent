"""
ZENIC-AGENTS - Statement Loops Mixin

Loop and compound statement processing methods for the SymbolicExecutor:
- _process_for: Handle ast.For (bounded unrolling)
- _process_while: Handle ast.While (bounded unrolling)
- _process_try: Handle ast.Try (exception paths)
- _process_expr_stmt: Handle ast.Expr (expression statements)

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


class StatementLoopsMixin:
    """
    Mixin for SymbolicExecutor providing loop and compound statement processing methods.
    """

    # ----------------------------------------------------------------
    #  Loop & Compound Statement Processors
    # ----------------------------------------------------------------

    def _process_for(self, stmt, path):
        """
        Process ast.For with bounded unrolling (up to LOOP_UNROLL_LIMIT iterations).

        Creates paths for:
        - Loop body iteration 1
        - Loop body iteration 2
        - Loop exit (0 iterations)
        Each with appropriate path conditions on the loop variable.
        """
        all_paths = []

        # Get loop variable name
        if not isinstance(stmt.target, ast.Name):
            # Complex target; simplified handling
            return [path]
        loop_var = stmt.target.id

        # Determine iteration range if possible
        iter_concrete = None
        if isinstance(stmt.iter, ast.Call):
            func_name = self._get_call_name(stmt.iter)
            if func_name == "range" and stmt.iter.args:
                # range(n) or range(start, stop) or range(start, stop, step)
                args_concrete = [self._try_eval_concrete(a, path) for a in stmt.iter.args]
                if all(a is not None for a in args_concrete):
                    try:
                        iter_concrete = list(range(*args_concrete))
                    except (TypeError, ValueError):
                        iter_concrete = None

        # Path for 0 iterations (loop exit immediately)
        exit_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        # Add condition: loop didn't execute (i.e., iterator was empty)
        if iter_concrete is not None and len(iter_concrete) == 0:
            # This path is the only possibility
            return [exit_path]
        exit_path.add_condition(f"LOOP_EMPTY_{loop_var}")
        all_paths.append(exit_path)

        # Bounded unrolling
        current_paths = [path]
        for iteration in range(self.LOOP_UNROLL_LIMIT):
            next_paths = []
            for cp in current_paths:
                # Create path for this iteration
                iter_path = SymbolicPath(
                    condition=list(cp.condition),
                    variables=dict(cp.variables),
                    is_pruned=cp.is_pruned,
                    z3_conditions=list(cp.z3_conditions),
                    assignments=list(cp.assignments),
                    return_values=list(cp.return_values)
                )

                # Set loop variable value
                if iter_concrete is not None and iteration < len(iter_concrete):
                    loop_val = iter_concrete[iteration]
                    iter_path.variables[loop_var] = SymbolicValue(
                        name=loop_var, var_type="int", concrete=loop_val
                    )
                    # Z3: constrain loop variable
                    if HAS_Z3:
                        z3_var = self._get_or_create_z3_var(loop_var, "int")
                        if z3_var is not None and len(iter_path.z3_conditions) < SymbolicPath.MAX_Z3_CONDITIONS:
                            iter_path.z3_conditions.append(z3_var == loop_val)
                else:
                    iter_path.variables[loop_var] = SymbolicValue(
                        name=loop_var, var_type="int"
                    )

                iter_path.add_condition(f"LOOP_ITER_{loop_var}_{iteration}")
                iter_path.add_assignment(loop_var, f"iter_{iteration}")

                # Process loop body
                body_paths = self._process_stmts(stmt.body, iter_path)
                next_paths.extend(body_paths)

            current_paths = next_paths
            if not current_paths:
                break

            # After last unrolled iteration, add exit paths
            if iteration == self.LOOP_UNROLL_LIMIT - 1:
                for cp in current_paths:
                    exit_after = SymbolicPath(
                        condition=list(cp.condition),
                        variables=dict(cp.variables),
                        is_pruned=cp.is_pruned,
                        z3_conditions=list(cp.z3_conditions),
                        assignments=list(cp.assignments),
                        return_values=list(cp.return_values)
                    )
                    exit_after.add_condition(f"LOOP_EXIT_{loop_var}")
                    all_paths.append(exit_after)
            else:
                # For intermediate iterations, also create exit paths
                for cp in current_paths:
                    exit_after = SymbolicPath(
                        condition=list(cp.condition),
                        variables=dict(cp.variables),
                        is_pruned=cp.is_pruned,
                        z3_conditions=list(cp.z3_conditions),
                        assignments=list(cp.assignments),
                        return_values=list(cp.return_values)
                    )
                    exit_after.add_condition(f"LOOP_EXIT_{loop_var}_after_{iteration + 1}")
                    all_paths.append(exit_after)

        all_paths.extend(current_paths)
        return all_paths[:self.k_path_limit]

    def _process_while(self, stmt, path):
        """
        Process ast.While with bounded unrolling (up to LOOP_UNROLL_LIMIT iterations).

        Creates paths for:
        - Condition false (loop exit)
        - Condition true + body (iteration 1)
        - Condition true + body (iteration 2)
        """
        all_paths = []

        # Path for 0 iterations (condition false immediately)
        false_str, false_z3 = self._encode_z3_condition(stmt.test, path, negate=True)
        exit_path = SymbolicPath(
            condition=path.condition + [false_str],
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        if false_z3 is not None:
            exit_path.add_condition(false_str, false_z3)
        else:
            exit_path.add_condition(false_str)
        all_paths.append(exit_path)

        # Bounded unrolling
        current_paths = [path]
        for iteration in range(self.LOOP_UNROLL_LIMIT):
            next_paths = []
            for cp in current_paths:
                # Condition true path
                true_str, true_z3 = self._encode_z3_condition(stmt.test, cp, negate=False)
                iter_path = SymbolicPath(
                    condition=cp.condition + [true_str],
                    variables=dict(cp.variables),
                    is_pruned=cp.is_pruned,
                    z3_conditions=list(cp.z3_conditions),
                    assignments=list(cp.assignments),
                    return_values=list(cp.return_values)
                )
                if true_z3 is not None:
                    iter_path.add_condition(true_str, true_z3)
                else:
                    iter_path.add_condition(true_str)

                iter_path.add_condition(f"WHILE_ITER_{iteration}")

                # Process loop body
                body_paths = self._process_stmts(stmt.body, iter_path)
                next_paths.extend(body_paths)

                # Also add exit path after this iteration
                exit_str, exit_z3 = self._encode_z3_condition(stmt.test, cp, negate=True)
                exit_iter_path = SymbolicPath(
                    condition=cp.condition + [exit_str],
                    variables=dict(cp.variables),
                    is_pruned=cp.is_pruned,
                    z3_conditions=list(cp.z3_conditions),
                    assignments=list(cp.assignments),
                    return_values=list(cp.return_values)
                )
                if exit_z3 is not None:
                    exit_iter_path.add_condition(exit_str, exit_z3)
                else:
                    exit_iter_path.add_condition(exit_str)
                all_paths.append(exit_iter_path)

            current_paths = next_paths
            if not current_paths:
                break

        # Add remaining paths (after all unrolled iterations)
        all_paths.extend(current_paths)
        return all_paths[:self.k_path_limit]

    def _process_try(self, stmt, path):
        """Process ast.Try: create paths for try body and each handler."""
        all_paths = []

        # Try body (normal execution)
        try_paths = self._process_stmts(stmt.body, path)
        all_paths.extend(try_paths)

        # Each except handler
        for handler in stmt.handlers:
            handler_path = SymbolicPath(
                condition=list(path.condition),
                variables=dict(path.variables),
                is_pruned=path.is_pruned,
                z3_conditions=list(path.z3_conditions),
                assignments=list(path.assignments),
                return_values=list(path.return_values)
            )
            exc_type = "Exception"
            if handler.type:
                exc_type = self._symbolize_expr(handler.type, path)
            handler_path.add_condition(f"EXCEPTION_{exc_type}")

            if handler.name:
                handler_path.variables[handler.name] = SymbolicValue(
                    name=handler.name, var_type="exception"
                )
                handler_path.add_assignment(handler.name, f"caught_{exc_type}")

            handler_body_paths = self._process_stmts(handler.body, handler_path)
            all_paths.extend(handler_body_paths)

        # Else clause (if no exception)
        if stmt.orelse:
            else_paths = self._process_stmts(stmt.orelse, try_paths[0] if try_paths else path)
            all_paths.extend(else_paths)

        # Finally clause
        if stmt.finalbody:
            final_paths = []
            for p in all_paths:
                fp = self._process_stmts(stmt.finalbody, p)
                final_paths.extend(fp)
            all_paths = final_paths

        return all_paths

    def _process_expr_stmt(self, stmt, path):
        """Process ast.Expr statement (e.g., standalone function calls)."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        if isinstance(stmt.value, ast.Call):
            call_name = self._get_call_name(stmt.value)
            base_name = call_name.split('.')[-1] if '.' in call_name else call_name
            if base_name in self.IO_OPERATIONS:
                new_path.is_pruned = True
                new_path.variables[f"_mocked_{call_name}"] = SymbolicValue(
                    name=f"_mocked_{call_name}",
                    var_type="mocked_io",
                    constraint=lambda x: True
                )

        return new_path
