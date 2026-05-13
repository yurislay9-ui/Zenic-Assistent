"""Mixin: Non-Python language validation for ReflexionSandbox."""

import re

from ._imports import SandboxResult


class OtherValidationMixin:
    """Mixin providing basic validation for non-Python languages."""

    def _validate_other(self, code, language, target_name):
        """Validacion basica para lenguajes no-Python."""
        if not code.strip():
            return SandboxResult(status="FAIL_SYNTAX", error_message="Empty code")

        warnings = []
        # Verificar balance de delimitadores
        for open_ch, close_ch in [('{', '}'), ('(', ')'), ('[', ']')]:
            opens = code.count(open_ch)
            closes = code.count(close_ch)
            if opens != closes:
                return SandboxResult(
                    status="FAIL_SYNTAX",
                    error_message=f"Unbalanced '{open_ch}'={opens}, '{close_ch}'={closes}"
                )

        # Ejecucion simbolica simplificada para otros lenguajes
        symbolic_result = self._symbolic_executor.execute_symbolic(
            code, language, target_name
        )

        paths_explored = symbolic_result["metrics"]["paths_explored"]
        paths_pruned = symbolic_result["metrics"]["paths_pruned"]

        if paths_explored > self.k_path_limit:
            return SandboxResult(
                status="FAIL_K_PATH",
                error_message=(
                    f"K-Paths ({paths_explored}) exceeds limit ({self.k_path_limit}). "
                    f"Subdivide operation into smaller units."
                ),
                warnings=warnings + symbolic_result.get("warnings", []),
                metrics={"k_paths": paths_explored},
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Verificar que hay al menos una definicion
        patterns = {
            "kotlin": r'(?:fun|class)\s+\w+',
            "go": r'func\s+\w+',
            "javascript": r'(?:function|class|const|let)\s+\w+',
            "typescript": r'(?:function|class|const|let)\s+\w+',
            "java": r'(?:public|private|protected)\s+(?:static\s+)?(?:class|void)\s+\w+',
            "rust": r'(?:pub\s+)?fn\s+\w+',
        }
        pattern = patterns.get(language, r'(?:def|function|fun|func)\s+\w+')
        if not re.search(pattern, code):
            warnings.append("No function/class definitions found in code")

        return SandboxResult(
            status="PASS",
            warnings=warnings + symbolic_result.get("warnings", []),
            metrics={"k_paths": paths_explored, "sandbox_isolated": True},
            paths_explored=paths_explored,
            paths_pruned=paths_pruned
        )
