"""
ZENIC-AGENTS - Symbolic Executor Core

Core SymbolicExecutor class with:
- execute_symbolic: Main entry point for bounded symbolic execution
- _analyze_function_symbolic: Per-function symbolic analysis
- _process_stmts: Statement-by-statement processing with path forking

Helper methods are in executor_helpers.py.
Statement processors are in statement_processors.py and statement_loops.py.

This module composes all mixin classes into the final SymbolicExecutor.
"""

import ast
import logging

logger = logging.getLogger(__name__)

from .types import SymbolicValue, SymbolicPath
from .z3_bridge import Z3BridgeMixin
from .statement_processors import StatementProcessorMixin
from .statement_loops import StatementLoopsMixin
from .executor_helpers import ExecutorHelpersMixin
from .violations import ViolationCheckerMixin
from .concrete_gen import ConcreteGenMixin


class SymbolicExecutor(
    Z3BridgeMixin,
    StatementProcessorMixin,
    StatementLoopsMixin,
    ExecutorHelpersMixin,
    ViolationCheckerMixin,
    ConcreteGenMixin,
):
    """
    Ejecutor Simbolico Acotado real.

    Implementa la ejecucion simbolica del Nivel 6 como especifica el documento:
    - Estados simbolicos (valores abstractos con constraints)
    - Path conditions por cada rama (string + Z3 cuando disponible)
    - Path Pruning de side effects (I/O -> Mock)
    - K-Path limiting (radio de exploracion)
    - Bounded execution (profundidad limitada)
    - Assignment tracking (mutaciones de estado simbolico)
    - Return value tracking (verificacion de retorno consistente)
    - Bounded loop unrolling (hasta 2 iteraciones)
    - Violation detection: div-by-zero, index OOB, type mismatch, uninitialized, None deref
    """

    # Operaciones que son side effects y deben ser podadas
    IO_OPERATIONS = {
        "open", "read", "write", "input", "print",
        "fetch", "urlopen", "request",
        "execute", "cursor", "query",
        "connect", "send", "recv",
    }

    # Bounded loop unrolling: max iterations
    LOOP_UNROLL_LIMIT = 2

    # Incompatible type pairs for binary operations
    INCOMPATIBLE_TYPES = {
        frozenset({"str", "int"}), frozenset({"str", "float"}),
        frozenset({"list", "int"}), frozenset({"dict", "int"}),
        frozenset({"None", "int"}), frozenset({"None", "float"}),
        frozenset({"None", "str"}), frozenset({"None", "list"}),
    }

    def __init__(self, k_path_limit=10, max_depth=20):
        self.k_path_limit = k_path_limit
        self.max_depth = max_depth
        self.paths_explored = 0
        self.paths_pruned = 0
        self.results = []
        self._z3_vars = {}  # Cache of Z3 variable objects per function
        self._func_return_type = {}  # Inferred return types per function

    def execute_symbolic(self, code, language="python", target_name=""):
        """
        Ejecuta analisis simbolico acotado sobre codigo Python.

        Returns:
            dict con paths, violations, warnings, metrics
        """
        self.paths_explored = 0
        self.paths_pruned = 0
        self.results = []
        self._z3_vars = {}
        self._func_return_type = {}

        if language != "python":
            return self._symbolic_regex(code, language, target_name)

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "status": "FAIL_SYNTAX",
                "paths": [],
                "violations": [],
                "warnings": [f"Syntax error: {e.msg} at line {e.lineno}"],
                "metrics": {"paths_explored": 0, "paths_pruned": 0}
            }

        # Pre-scan: build a map of function names for call resolution
        func_map = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_map[node.name] = node
        self._func_map = func_map

        # Analizar cada funcion
        all_paths = []
        all_violations = []
        all_warnings = []
        total_pruned = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._z3_vars = {}  # Reset Z3 var cache per function
                func_paths = self._analyze_function_symbolic(node, code)
                all_paths.extend(func_paths)

                # Verificar violaciones en cada camino
                for path in func_paths:
                    if path.is_pruned:
                        total_pruned += 1
                    violations = self._check_path_violations(path, node.name)
                    all_violations.extend(violations)

                # Check return consistency across all paths of this function
                return_warnings = self._check_return_consistency(func_paths, node.name)
                all_warnings.extend(return_warnings)

        self.paths_explored = len(all_paths)
        self.paths_pruned = total_pruned

        # Verificar K-Path limit
        if self.paths_explored > self.k_path_limit:
            all_warnings.append(
                f"K-Paths ({self.paths_explored}) exceeds limit ({self.k_path_limit}). "
                f"Subdivide operation into smaller units."
            )

        return {
            "status": "PASS" if not all_violations else "VIOLATIONS_FOUND",
            "paths": all_paths,
            "violations": all_violations,
            "warnings": all_warnings,
            "metrics": {
                "paths_explored": self.paths_explored,
                "paths_pruned": self.paths_pruned,
                "total_paths": len(all_paths),
                "feasible_paths": sum(1 for p in all_paths if p.is_feasible()),
            }
        }

    # ----------------------------------------------------------------
    #  Function Analysis
    # ----------------------------------------------------------------

    def _analyze_function_symbolic(self, func_node, source_code):
        """
        Analiza simbolicamente una funcion, explorando todos los caminos.

        Ahora con:
        - Tracking de asignaciones (ast.Assign, ast.AugAssign)
        - Handling de returns (ast.Return)
        - Bounded loop unrolling (ast.For, ast.While)
        - Z3 condition encoding
        """
        # Inicializar estado simbolico con parametros
        initial_state = {}
        for arg in func_node.args.args:
            arg_type = "any"
            if arg.annotation:
                arg_type = self._annotation_to_type(arg.annotation)
            initial_state[arg.arg] = SymbolicValue(
                name=arg.arg,
                var_type=arg_type
            )
            # Pre-create Z3 vars for parameters
            self._get_or_create_z3_var(arg.arg, arg_type)

        # Process function body statement by statement
        initial_path = SymbolicPath(
            variables=dict(initial_state),
            z3_conditions=[],
            assignments=[],
            return_values=[]
        )
        paths = self._process_stmts(func_node.body, initial_path)

        return paths[:self.k_path_limit]

    def _process_stmts(self, stmts, current_path):
        """
        Process a list of statements, returning a list of resulting SymbolicPaths.

        This is the core of the symbolic execution engine, handling each
        statement type and forking paths at branches.
        """
        worklist = [(list(stmts), current_path)]
        completed_paths = []

        while worklist:
            remaining_stmts, path = worklist.pop(0)

            if len(completed_paths) >= self.k_path_limit:
                break

            if not remaining_stmts:
                completed_paths.append(path)
                continue

            stmt = remaining_stmts[0]
            rest = remaining_stmts[1:]

            # --- ast.Assign: x = expr ---
            if isinstance(stmt, ast.Assign):
                new_path = self._process_assign(stmt, path)
                worklist.append((rest, new_path))

            # --- ast.AugAssign: x += expr ---
            elif isinstance(stmt, ast.AugAssign):
                new_path = self._process_aug_assign(stmt, path)
                worklist.append((rest, new_path))

            # --- ast.Return ---
            elif isinstance(stmt, ast.Return):
                ret_path = self._process_return(stmt, path)
                completed_paths.append(ret_path)

            # --- ast.If ---
            elif isinstance(stmt, ast.If):
                branch_paths = self._process_if(stmt, path)
                for bp in branch_paths:
                    if bp.is_feasible():
                        # Process true body then rest / false body then rest
                        worklist.append((rest, bp))
                    else:
                        self.paths_pruned += 1

            # --- ast.For (bounded unrolling) ---
            elif isinstance(stmt, ast.For):
                loop_paths = self._process_for(stmt, path)
                for lp in loop_paths:
                    worklist.append((rest, lp))

            # --- ast.While (bounded unrolling) ---
            elif isinstance(stmt, ast.While):
                loop_paths = self._process_while(stmt, path)
                for lp in loop_paths:
                    worklist.append((rest, lp))

            # --- ast.Expr (expression statement, e.g. function calls) ---
            elif isinstance(stmt, ast.Expr):
                new_path = self._process_expr_stmt(stmt, path)
                worklist.append((rest, new_path))

            # --- ast.Pass ---
            elif isinstance(stmt, ast.Pass):
                worklist.append((rest, path))

            # --- ast.Break ---
            elif isinstance(stmt, ast.Break):
                # Exit current loop - just complete the path here
                completed_paths.append(path)

            # --- ast.Continue ---
            elif isinstance(stmt, ast.Continue):
                # Would need loop context; simplified: skip
                worklist.append((rest, path))

            # --- ast.Try ---
            elif isinstance(stmt, ast.Try):
                # Process try body, and create alternative paths for each handler
                try_paths = self._process_try(stmt, path)
                for tp in try_paths:
                    worklist.append((rest, tp))

            # --- ast.Raise ---
            elif isinstance(stmt, ast.Raise):
                # Path ends with exception
                exc_desc = "raised_exception"
                if stmt.exc:
                    exc_desc = self._symbolize_expr(stmt.exc, path)
                new_path = SymbolicPath(
                    condition=list(path.condition),
                    variables=dict(path.variables),
                    is_pruned=path.is_pruned,
                    z3_conditions=list(path.z3_conditions),
                    assignments=list(path.assignments),
                    return_values=list(path.return_values)
                )
                new_path.add_return(f"raise {exc_desc}", "exception")
                completed_paths.append(new_path)

            # --- Other statements: skip but continue ---
            else:
                worklist.append((rest, path))

        return completed_paths[:self.k_path_limit]
