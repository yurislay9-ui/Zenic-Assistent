"""
A24 SyntaxValidator — SINGLE RESPONSIBILITY: Validate code syntax via AST parsing.

Deterministic. No AI.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import SyntaxResult, ValidationIssue


class SyntaxValidator(BaseAgent[SyntaxResult]):
    """
    A24: Validate code syntax.

    Single Responsibility: Syntax validation ONLY.
    Method: ast.parse() for Python, brace balance for JS/TS.
    Fallback: Return valid=False (fail-closed for safety).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A24_SyntaxValidator", **kwargs)

    def execute(self, input_data: Any) -> SyntaxResult:
        """
        Validate code syntax.

        input_data should be a dict with:
          - 'code': str
          - 'language': str (default: "python")
        """
        code = ""
        language = "python"

        if isinstance(input_data, dict):
            code = input_data.get("code", "")
            language = input_data.get("language", "python")
        elif isinstance(input_data, str):
            code = input_data

        if not code:
            return SyntaxResult(valid=True, source="deterministic")

        if language == "python":
            return self._validate_python(code)
        elif language in ("javascript", "typescript"):
            return self._validate_js(code)
        else:
            # For other languages, basic brace balance check
            return self._validate_braces(code)

    def _validate_python(self, code: str) -> SyntaxResult:
        """Validate Python code using ast.parse()."""
        errors = []
        try:
            tree = ast.parse(code)

            # Check for missing returns on all paths
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not self._function_returns_on_all_paths(node):
                        errors.append(ValidationIssue(
                            severity="warning",
                            code="missing_return",
                            message=f"Function '{node.name}' may not return on all paths",
                            line=node.lineno,
                        ))

                # Check for resource leaks (open without with)
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "open":
                        errors.append(ValidationIssue(
                            severity="warning",
                            code="resource_leak",
                            message="open() without 'with' context manager may leak resources",
                            line=node.lineno,
                        ))

                # Check for bare except
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    errors.append(ValidationIssue(
                        severity="warning",
                        code="bare_except",
                        message="Bare except catches all exceptions including SystemExit",
                        line=node.lineno,
                    ))

            return SyntaxResult(
                valid=True,
                errors=errors,
                line_numbers=[e.line for e in errors],
                source="deterministic",
            )

        except SyntaxError as e:
            errors.append(ValidationIssue(
                severity="error",
                code="syntax_error",
                message=str(e.msg),
                line=e.lineno or 0,
            ))
            return SyntaxResult(
                valid=False,
                errors=errors,
                line_numbers=[e.lineno or 0],
                source="deterministic",
            )

    def _validate_js(self, code: str) -> SyntaxResult:
        """Basic JS/TS validation via brace balance."""
        return self._validate_braces(code)

    def _validate_braces(self, code: str) -> SyntaxResult:
        """Check brace/bracket/paren balance."""
        stack = []
        pairs = {"(": ")", "{": "}", "[": "]"}
        errors = []

        for i, char in enumerate(code):
            if char in pairs:
                stack.append((char, i))
            elif char in pairs.values():
                if not stack:
                    line = code[:i].count("\n") + 1
                    errors.append(ValidationIssue(
                        severity="error",
                        code="unmatched_brace",
                        message=f"Unmatched closing '{char}'",
                        line=line,
                    ))
                elif pairs[stack[-1][0]] != char:
                    line = code[:i].count("\n") + 1
                    errors.append(ValidationIssue(
                        severity="error",
                        code="mismatched_brace",
                        message=f"Expected '{pairs[stack[-1][0]]}' but found '{char}'",
                        line=line,
                    ))
                else:
                    stack.pop()

        for char, pos in stack:
            line = code[:pos].count("\n") + 1
            errors.append(ValidationIssue(
                severity="error",
                code="unclosed_brace",
                message=f"Unclosed '{char}'",
                line=line,
            ))

        return SyntaxResult(
            valid=len(errors) == 0,
            errors=errors,
            line_numbers=[e.line for e in errors],
            source="deterministic",
        )

    @staticmethod
    def _function_returns_on_all_paths(func_node: ast.FunctionDef) -> bool:
        """Check if a function returns on all paths (simple heuristic).

        - No return at all = void function → True (OK)
        - Has return with value but may fall through → False (warning)
        - All paths return → True (OK)
        """
        has_return = False
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value is not None:
                has_return = True
                break

        # No return statements → void function, that's fine
        if not has_return:
            return True

        # Has returns — check if function might fall through without returning.
        # Simple heuristic: if the function body's last statement is a Return,
        # or all branches of the last if/else return, it's likely complete.
        # For simplicity, we check if there's a top-level return at the end.
        last_stmt = func_node.body[-1] if func_node.body else None
        if isinstance(last_stmt, ast.Return):
            return True

        # Check if the last statement is an if/else where both branches return
        if isinstance(last_stmt, ast.If):
            if_return = False
            else_return = False
            if last_stmt.body and isinstance(last_stmt.body[-1], ast.Return):
                if_return = True
            if last_stmt.orelse and isinstance(last_stmt.orelse[-1], ast.Return):
                else_return = True
            if if_return and else_return:
                return True

        # Has returns but might not return on all paths
        return False

    def fallback(self, input_data: Any) -> SyntaxResult:
        return SyntaxResult(valid=False, source="fallback", errors=[
            ValidationIssue(severity="warning", code="validation_degraded",
                           message="Syntax validation unavailable — treating as invalid for safety")
        ])
