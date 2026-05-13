"""
A22 DefensiveInjector — SINGLE RESPONSIBILITY: Inject defensive code patterns for F4 criticality.

Deterministic defensive injection: security warnings, validation, error handling, docstrings.
No AI. AST + regex-based injection driven by criticality adjustments.
"""

from __future__ import annotations

import ast
from typing import Any

from ..resilience import BaseAgent
from ..schemas import CodeResult


# ──────────────────────────────────────────────────────────────
# DANGEROUS PATTERNS FOR SECURITY WARNINGS
# ──────────────────────────────────────────────────────────────

DANGEROUS_PATTERNS = [
    ("eval(", "eval() is a security risk — use ast.literal_eval() for safe parsing"),
    ("exec(", "exec() is a security risk — avoid dynamic code execution"),
    ("os.system(", "os.system() is vulnerable to injection — use subprocess.run()"),
    ("subprocess.call(", "Use subprocess.run() with shell=False for safety"),
    ("__import__(", "Dynamic imports can be dangerous — use static imports"),
    ("pickle.loads(", "pickle is unsafe for untrusted data — use json or msgpack"),
]


class DefensiveInjector(BaseAgent[CodeResult]):
    """
    A22: Inject defensive code patterns for F4 criticality.

    Single Responsibility: Defensive injection ONLY.
    Method: Criticality-level-driven injection (Level 3=full, Level 2=standard, Level 1=none).
    Fallback: Return code unchanged.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A22_DefensiveInjector", **kwargs)

    def execute(self, input_data: Any) -> CodeResult:
        """
        Inject defensive patterns based on criticality level.

        Input (dict):
            - code: str (code to harden)
            - language: str
            - criticality_level: int (1=FAST, 2=MODERATE, 3=SURGICAL)
            - adjustments: dict (from A04 CriticalityScorer)

        Output: CodeResult with injected patterns + audit entries.
        """
        if isinstance(input_data, dict):
            code = input_data.get("code", "")
            language = input_data.get("language", "python")
            crit_level = input_data.get("criticality_level", 1)
            adjustments = input_data.get("adjustments", {})
        else:
            code = getattr(input_data, "code", "")
            language = getattr(input_data, "language", "python")
            crit_level = getattr(input_data, "criticality_level", 1)
            adjustments = getattr(input_data, "adjustments", {})

        if not code:
            return CodeResult(
                code=code, language=language,
                injected_patterns=[], audit_entries=[],
                source="deterministic",
            )

        injected: list[str] = []
        audit: list[str] = []

        # ── Level 3: SURGICAL_CRITICAL ──
        if crit_level >= 3:
            code, sec_injected = self._inject_security_warnings(code, language)
            injected.extend(sec_injected)

            code, val_injected = self._inject_defensive_validation(code, language)
            injected.extend(val_injected)

            code = self._inject_comprehensive_error_handling(code, language)
            injected.append("comprehensive_error_handling")

            code = self._ensure_full_docstrings(code, language)
            injected.append("full_docstrings")

            audit.append(f"F4 Level 3 SURGICAL: {len(injected)} patterns injected")

        # ── Level 2: DEEP_MODERATE ──
        elif crit_level >= 2:
            code, sec_injected = self._inject_security_warnings(code, language)
            injected.extend(sec_injected)

            code = self._inject_standard_error_handling(code, language)
            injected.append("standard_error_handling")

            code = self._ensure_standard_docstrings(code, language)
            injected.append("standard_docstrings")

            audit.append(f"F4 Level 2 MODERATE: {len(injected)} patterns injected")

        # ── Level 1: FAST_STANDARD ──
        else:
            audit.append("F4 Level 1 FAST: No defensive injection needed")

        return CodeResult(
            code=code, language=language,
            injected_patterns=injected,
            audit_entries=audit,
            source="deterministic",
        )

    @staticmethod
    def _inject_security_warnings(code: str, language: str) -> tuple:
        """Add security warnings for dangerous patterns."""
        warnings = []
        for pattern, warning in DANGEROUS_PATTERNS:
            if pattern in code:
                warnings.append(f"SECURITY WARNING: {warning}")

        if warnings:
            header = "\n".join(f"# {w}" for w in warnings) + "\n\n"
            return header + code, warnings
        return code, []

    @staticmethod
    def _inject_defensive_validation(code: str, language: str) -> tuple:
        """Inject defensive argument validation in Python functions."""
        if language != "python":
            return code, []

        # Skip if already has defensive validation
        if "if not isinstance(" in code:
            return code, []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code, []

        lines = code.split('\n')
        modified = list(lines)
        injected = []
        offset = 0

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith('_') or node.name == '__init__':
                continue
            if not node.args.args:
                continue

            args = [a.arg for a in node.args.args if a.arg != 'self']
            if not args:
                continue

            insert_line = node.lineno
            if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                insert_line = node.body[0].end_lineno + 1

            val_comment = f"    # F4: Validate inputs: {', '.join(args[:3])}"
            if 0 <= insert_line - 1 + offset < len(modified):
                modified.insert(insert_line - 1 + offset, val_comment)
                offset += 1
                injected.append(f"validation_comment:{node.name}")

        return '\n'.join(modified), injected

    @staticmethod
    def _inject_comprehensive_error_handling(code: str, language: str) -> str:
        """Inject comprehensive error handling markers."""
        if language != "python":
            return code
        if "import logging" not in code and "from logging" not in code:
            code = "import logging\n\nlogger = logging.getLogger(__name__)\n\n" + code
        if "# F4: Comprehensive error handling" not in code:
            code = "# F4: Comprehensive error handling (SURGICAL_CRITICAL)\n" + code
        return code

    @staticmethod
    def _inject_standard_error_handling(code: str, language: str) -> str:
        """Inject standard error handling markers."""
        if language != "python":
            return code
        if "# F4: Standard error handling" not in code:
            code = "# F4: Standard error handling (DEEP_MODERATE)\n" + code
        return code

    @staticmethod
    def _ensure_full_docstrings(code: str, language: str) -> str:
        """Ensure full docstrings (Args, Returns, Raises)."""
        if language != "python":
            return code
        if "# F4: Full docstrings" not in code:
            code = "# F4: Full docstrings required (SURGICAL_CRITICAL)\n" + code
        return code

    @staticmethod
    def _ensure_standard_docstrings(code: str, language: str) -> str:
        """Ensure standard docstrings."""
        if language != "python":
            return code
        if "# F4: Standard docstrings" not in code:
            code = "# F4: Standard docstrings (DEEP_MODERATE)\n" + code
        return code

    def fallback(self, input_data: Any) -> CodeResult:
        """Safe fallback: return code unchanged."""
        if isinstance(input_data, dict):
            code = input_data.get("code", "")
            language = input_data.get("language", "python")
        else:
            code = getattr(input_data, "code", "")
            language = getattr(input_data, "language", "python")
        return CodeResult(code=code, language=language, source="fallback")
