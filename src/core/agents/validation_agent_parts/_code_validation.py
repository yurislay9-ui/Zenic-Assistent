"""
ValidationAgent code validation mixin — _validate_code, _validate_python_ast.
"""

import re
import ast
import logging
from typing import List

from ._imports import (
    ValidationOutput, ValidationIssue,
    SECURITY_PATTERNS, QUALITY_PATTERNS,
    logger,
)


class CodeValidationMixin:
    """Code validation methods for ValidationAgent."""

    # ============================================================
    #  CODE VALIDATION (deterministic)
    # ============================================================

    def _validate_code(self, code: str, language: str,
                       rules: List[str]) -> ValidationOutput:
        """Validación determinista de código."""
        if not code:
            return ValidationOutput(
                is_valid=True, issues=[],
                suggestions=["No code provided for validation"],
                risk_score=0.0,
            )

        issues = []

        # Security patterns (always checked)
        for pattern, code_id, message, severity in SECURITY_PATTERNS:
            matches = list(re.finditer(pattern, code, re.IGNORECASE))
            for match in matches:
                line_num = code[:match.start()].count('\n') + 1
                issues.append(ValidationIssue(
                    severity=severity,
                    code=code_id,
                    message=message,
                    line=line_num,
                    suggestion=self._get_fix_suggestion(code_id),
                ))

        # Quality patterns (if rules include "quality")
        if not rules or "quality" in rules or "all" in rules:
            for pattern, code_id, message, severity in QUALITY_PATTERNS:
                matches = list(re.finditer(pattern, code, re.IGNORECASE))
                for match in matches:
                    line_num = code[:match.start()].count('\n') + 1
                    issues.append(ValidationIssue(
                        severity=severity,
                        code=code_id,
                        message=message,
                        line=line_num,
                        suggestion=self._get_fix_suggestion(code_id),
                    ))

        # Python-specific AST analysis
        if language == "python":
            issues.extend(self._validate_python_ast(code))

        # Calculate risk score
        risk_score = self._calculate_risk_score(issues)

        # Generate suggestions
        suggestions = self._generate_suggestions(issues)

        return ValidationOutput(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=issues,
            suggestions=suggestions,
            risk_score=risk_score,
        )

    def _validate_python_ast(self, code: str) -> List[ValidationIssue]:
        """Validación de Python via AST analysis."""
        issues = []
        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                # Missing return in function that returns elsewhere
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    has_return = any(
                        isinstance(n, ast.Return) and n.value is not None
                        for n in ast.walk(node)
                    )
                    if has_return and node.body:
                        last_stmt = node.body[-1]
                        if not isinstance(last_stmt, (ast.Return, ast.Raise)):
                            issues.append(ValidationIssue(
                                severity="warning",
                                code="missing_return",
                                message=f"Function '{node.name}' may not return on all paths",
                                line=node.lineno,
                                suggestion="Add a return statement at the end of the function",
                            ))

                    # Resource leak: open() without with
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            func = getattr(child, 'func', None)
                            if isinstance(func, ast.Name) and func.id == 'open':
                                call_line = child.lineno
                                issues.append(ValidationIssue(
                                    severity="warning",
                                    code="resource_leak",
                                    message=f"Potential resource leak: open() without 'with' in '{node.name}'",
                                    line=call_line,
                                    suggestion="Use 'with open(...) as f:' to ensure file closure",
                                ))

                # Bare except
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="bare_except",
                        message="Bare 'except:' catches all exceptions including SystemExit",
                        line=node.lineno,
                        suggestion="Use 'except Exception:' instead",
                    ))

        except SyntaxError as e:
            issues.append(ValidationIssue(
                severity="error",
                code="syntax_error",
                message=f"Syntax error: {str(e)}",
                line=e.lineno or 0,
                suggestion="Fix the syntax error before proceeding",
            ))

        return issues
