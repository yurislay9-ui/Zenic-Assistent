"""Mixin: Python validation for ReflexionSandbox."""

import ast

from ._imports import logger, SandboxResult


class PythonValidationMixin:
    """Mixin providing full Python validation with symbolic execution."""

    def _validate_python(self, code, target_name):
        """Validacion completa de codigo Python con ejecucion simbolica AISLADA."""
        # Fase 1: Parseo AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return SandboxResult(
                status="FAIL_SYNTAX",
                error_message=f"Syntax error line {e.lineno}: {e.msg}",
                error_node={"line": e.lineno, "offset": e.offset}
            )

        warnings = []
        metrics = {"functions": 0, "classes": 0, "max_complexity": 0,
                   "imports": 0, "calls": 0}
        paths_explored = 0
        paths_pruned = 0

        # Fase 2: Analisis estructural
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                metrics["functions"] += 1
                complexity = self._cyclomatic(node)
                metrics["max_complexity"] = max(metrics["max_complexity"], complexity)
                if complexity > 10:
                    warnings.append(
                        f"Function '{node.name}' has complexity {complexity} (>10). "
                        f"Consider refactoring."
                    )
            elif isinstance(node, ast.ClassDef):
                metrics["classes"] += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                metrics["imports"] += 1
            elif isinstance(node, ast.Call):
                metrics["calls"] += 1

        # Fase 3: Ejecucion Simbolica Acotada Real
        symbolic_result = self._symbolic_executor.execute_symbolic(
            code, "python", target_name
        )

        paths_explored = symbolic_result["metrics"]["paths_explored"]
        paths_pruned = symbolic_result["metrics"]["paths_pruned"]
        metrics["k_paths"] = paths_explored
        metrics["feasible_paths"] = symbolic_result["metrics"].get("feasible_paths", 0)
        metrics["io_calls"] = paths_pruned

        # Agregar violaciones simbolicas como warnings
        for violation in symbolic_result.get("violations", []):
            proven_reachable = False
            for path in symbolic_result.get("paths", []):
                reachability = self._symbolic_executor.prove_violation_reachable(
                    violation, path
                )
                if reachability.get("reachable") is True:
                    counterexample = reachability.get("counterexample", {})
                    if counterexample:
                        warnings.append(
                            f"Symbolic (Z3 PROVEN): {violation} "
                            f"[counterexample: {counterexample}]"
                        )
                    else:
                        warnings.append(f"Symbolic (Z3 PROVEN): {violation}")
                    proven_reachable = True
                    break
                elif reachability.get("reachable") is False:
                    continue
            if not proven_reachable:
                warnings.append(f"Symbolic: {violation}")

        # Generar test inputs concretos para cada path factible
        concrete_test_inputs = []
        for path in symbolic_result.get("paths", []):
            if path.is_feasible() and not path.is_pruned:
                inputs_result = self._symbolic_executor.generate_concrete_inputs(path)
                if inputs_result.get("inputs"):
                    concrete_test_inputs.append(inputs_result["inputs"])

        if concrete_test_inputs:
            metrics["concrete_test_inputs"] = len(concrete_test_inputs)
            metrics["test_inputs_sample"] = concrete_test_inputs[:3]

        # Fase 4: Deteccion de side effects (I/O) - Path Pruning
        io_calls = self._detect_io_calls(tree)
        for call in io_calls:
            if not any(f"I/O side-effect" in w for w in warnings):
                warnings.append(f"I/O side-effect detected: {call} (mocked in execution)")
            paths_pruned += len(io_calls)

        # Fase 5: Deteccion de llamadas peligrosas
        dangerous_calls = self._detect_dangerous(tree)
        for call in dangerous_calls:
            warnings.append(f"Potentially dangerous operation: {call}")

        # Fase 6: K-Path check usando grafo de dependencias real
        kpath_result = self._kpath_analyzer.measure_dependency_depth(target_name)
        if kpath_result["exceeds_limit"]:
            return SandboxResult(
                status="FAIL_K_PATH",
                error_message=(
                    f"K-Paths ({kpath_result['nodes_affected']} nodes affected, "
                    f"depth {kpath_result['depth']}) exceeds limit ({self.k_path_limit}). "
                    f"Subdivide operation into smaller units."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Si no hay grafo en SQLite, usar la estimacion del codigo
        if kpath_result["nodes_affected"] == 0 and paths_explored > self.k_path_limit:
            return SandboxResult(
                status="FAIL_K_PATH",
                error_message=(
                    f"K-Paths ({paths_explored}) exceeds limit ({self.k_path_limit}). "
                    f"Subdivide operation into smaller units."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Fase 7: Ejecucion segura AISLADA con timeout real
        if dangerous_calls:
            warnings.append(f"Dangerous calls detected: {', '.join(dangerous_calls)}. Execution blocked.")
            return SandboxResult(
                status="FAIL_DANGEROUS",
                error_message=(
                    f"Dangerous code patterns detected: {', '.join(dangerous_calls)}. "
                    f"Execution blocked for safety. Remove or refactor these calls."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        exec_result, timed_out = self._enforcer.execute_with_timeout(
            self._isolated_exec, code, target_name
        )
        if timed_out:
            return SandboxResult(
                status="FAIL_TIMEOUT",
                error_message=(
                    f"Execution exceeded timeout ({self.timeout_seconds}s). "
                    f"Code may contain infinite loops or excessive computation."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )
        if exec_result and exec_result.get("error"):
            return SandboxResult(
                status="FAIL_RUNTIME",
                error_message=exec_result["error"],
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Agregar info de la ejecucion simbolica al resultado
        metrics["symbolic_paths"] = len(symbolic_result.get("paths", []))
        metrics["symbolic_violations"] = len(symbolic_result.get("violations", []))
        metrics["sandbox_isolated"] = True

        # Exportar path conditions como SMT-LIB2 para analisis externo
        if symbolic_result.get("paths"):
            smt_export = self._symbolic_executor.export_path_conditions_smt(
                symbolic_result["paths"], target_name
            )
            metrics["smt_path_count"] = len(smt_export)
            metrics["smt_paths_available"] = True

        return SandboxResult(
            status="PASS",
            warnings=warnings,
            metrics=metrics,
            paths_explored=paths_explored,
            paths_pruned=paths_pruned
        )
