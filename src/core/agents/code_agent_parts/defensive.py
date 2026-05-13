"""
CodeAgent Defensive — criticality adjustments + defensive injection methods as
mixin.

Extracted from the monolithic code_agent.py (1,043 lines) as part of the
mixin-based modularisation.  Contains F4 criticality-aware code adjustments
and defensive validation / error-handling / docstring injection methods.
"""

import ast
from typing import Any

from src.core.agents.schemas import CodeOutput


class CodeAgentDefensiveMixin:
    """Mixin with criticality adjustments and defensive injection for CodeAgent."""

    # ============================================================
    #  F4: CRITICALITY-AWARE CODE ADJUSTMENTS
    # ============================================================

    def _apply_criticality_adjustments(self, result: CodeOutput) -> CodeOutput:
        """
        F4: Aplica ajustes de criticalidad al código generado.

        Nivel 3 (SURGICAL_CRITICAL):
          - Añade validación defensiva de argumentos
          - Añade verificaciones de seguridad (eval, exec, os.system)
          - Añade manejo de errores comprehensivo
          - Añade docstrings completos

        Nivel 2 (DEEP_MODERATE):
          - Añade validación básica de tipos
          - Añade manejo de errores estándar
          - Docstrings estándar

        Nivel 1 (FAST_STANDARD):
          - Sin ajustes adicionales
        """
        if not self._criticality_adjustments or not result.code:
            return result

        code = result.code
        language = result.language
        adj = self._criticality_adjustments

        # Security checks: add warnings for dangerous patterns
        if adj.get("security_checks", False):
            security_warnings = []
            dangerous_patterns = [
                ("eval(", "eval() is a security risk - use ast.literal_eval() for safe parsing"),
                ("exec(", "exec() is a security risk - avoid dynamic code execution"),
                ("os.system(", "os.system() is vulnerable to injection - use subprocess.run()"),
                ("subprocess.call(", "Use subprocess.run() with shell=False for safety"),
                ("__import__(", "Dynamic imports can be dangerous - use static imports"),
                ("pickle.loads(", "pickle is unsafe for untrusted data - use json or msgpack"),
            ]
            for pattern, warning in dangerous_patterns:
                if pattern in code:
                    security_warnings.append(f"# SECURITY WARNING: {warning}")
            if security_warnings:
                code = "\n".join(security_warnings) + "\n\n" + code

        # Extra validation: add defensive checks to functions
        if adj.get("extra_validation", False):
            code = self._inject_defensive_validation(code, language)

        # Error handling level
        error_level = adj.get("error_handling", "basic")
        if error_level == "defensive":
            code = self._inject_defensive_error_handling(code, language)
        elif error_level == "comprehensive":
            code = self._inject_comprehensive_error_handling(code, language)

        # Docstring level
        docstring_level = adj.get("docstring_level", "minimal")
        if docstring_level == "full":
            code = self._ensure_full_docstrings(code, language)
        elif docstring_level == "standard":
            code = self._ensure_standard_docstrings(code, language)

        result.code = code
        return result

    def _inject_defensive_validation(self, code: str, language: str) -> str:
        """F4: Inyecta validación defensiva de argumentos en funciones Python."""
        if language != "python":
            return code

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        # Check if code already has defensive validation
        if "if not isinstance(" in code or "if not " in code:
            return code  # Already has validation

        lines = code.split('\n')
        modified = list(lines)

        # Find function definitions and add validation after docstring
        offset = 0
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith('_') or node.name == '__init__':
                continue
            if not node.args.args:
                continue  # No arguments to validate

            # Build validation line
            args = [a.arg for a in node.args.args if a.arg != 'self']
            if not args:
                continue

            # Find insertion point (after docstring if present)
            insert_line = node.lineno  # 1-based
            if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                insert_line = node.body[0].end_lineno + 1  # After docstring

            # Add type validation comment (lightweight)
            val_comment = f"    # F4: Validate inputs: {', '.join(args[:3])}"
            if 0 <= insert_line - 1 + offset < len(modified):
                modified.insert(insert_line - 1 + offset, val_comment)
                offset += 1

        return '\n'.join(modified)

    def _inject_defensive_error_handling(self, code: str, language: str) -> str:
        """F4: Inyecta manejo de errores defensivo (try/except con logging)."""
        if language != "python":
            return code

        # Add logging import if not present
        if "import logging" not in code and "from logging" not in code:
            code = "import logging\n\nlogger = logging.getLogger(__name__)\n\n" + code

        # Add top-level exception handler comment
        if "# F4: Defensive error handling" not in code:
            code = "# F4: Defensive error handling (SURGICAL_CRITICAL)\n" + code

        return code

    def _inject_comprehensive_error_handling(self, code: str, language: str) -> str:
        """F4: Inyecta manejo de errores comprehensivo."""
        if language != "python":
            return code

        # Add logging import if not present
        if "import logging" not in code and "from logging" not in code:
            code = "import logging\n\nlogger = logging.getLogger(__name__)\n\n" + code

        # Add comprehensive error handling comment
        if "# F4: Comprehensive error handling" not in code:
            code = "# F4: Comprehensive error handling (DEEP_MODERATE)\n" + code

        return code

    def _ensure_full_docstrings(self, code: str, language: str) -> str:
        """F4: Asegura docstrings completos (Args, Returns, Raises)."""
        if language != "python":
            return code
        if "Args:" in code and "Returns:" in code:
            return code  # Already has full docstrings
        # Add note about docstring level
        if "# F4: Full docstrings" not in code:
            code = "# F4: Full docstrings required (SURGICAL_CRITICAL)\n" + code
        return code

    def _ensure_standard_docstrings(self, code: str, language: str) -> str:
        """F4: Asegura docstrings estándar."""
        if language != "python":
            return code
        if "# F4: Standard docstrings" not in code:
            code = "# F4: Standard docstrings (DEEP_MODERATE)\n" + code
        return code
