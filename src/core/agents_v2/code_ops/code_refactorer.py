"""
A18 CodeRefactorer — SINGLE RESPONSIBILITY: Refactor/transform existing code.

Deterministic refactoring: AST-based type annotations, complexity notes.
No AI. Pure AST transformation for Python, passthrough for other languages.
"""

from __future__ import annotations

import ast
from typing import Any

from ..resilience import BaseAgent
from ..schemas import CodeResult


class CodeRefactorer(BaseAgent[CodeResult]):
    """
    A18: Refactor/transform existing code.

    Single Responsibility: Code refactoring ONLY.
    Method: AST-based deterministic transforms (Python), passthrough (others).
    Fallback: Return original code unchanged.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A18_CodeRefactorer", **kwargs)

    def execute(self, input_data: Any) -> CodeResult:
        """
        Refactor code: add type annotations, reduce complexity.

        Input (CodeRequest or dict):
            - existing_code: str (code to refactor)
            - requirements: str (refactoring goals)
            - language: str

        Output: CodeResult with refactored code + changes list.
        """
        if hasattr(input_data, "existing_code"):
            code = getattr(input_data, "existing_code", "")
            requirements = getattr(input_data, "requirements", "")
            language = getattr(input_data, "language", "python")
        elif isinstance(input_data, dict):
            code = input_data.get("existing_code", "")
            requirements = input_data.get("requirements", "")
            language = input_data.get("language", "python")
        else:
            code = str(input_data)
            requirements = ""
            language = "python"

        if not code:
            return CodeResult(
                code="# No existing code provided for transformation\n",
                language=language,
                changes=["Cannot refactor empty code"],
                source="deterministic",
            )

        # Python: AST-based refactoring
        if language == "python":
            return self._refactor_python(code, requirements)

        # Non-Python: passthrough with note
        return CodeResult(
            code=code,
            language=language,
            changes=[f"Refactoring note: {requirements[:200]} — LLM needed for non-Python transforms"],
            source="deterministic",
        )

    def _refactor_python(self, code: str, requirements: str) -> CodeResult:
        """AST-based deterministic Python refactoring."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return CodeResult(
                code=code, language="python",
                changes=["Cannot parse code — returning original"],
                source="deterministic",
            )

        changes: list[str] = []
        lines = code.split('\n')
        modified_lines = list(lines)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name
            func_start = node.lineno - 1
            args = [a.arg for a in node.args.args]
            has_return_annotation = node.returns is not None

            # Calculate cyclomatic complexity
            complexity = sum(
                1 for n in ast.walk(node)
                if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler))
            )

            # Add return type annotation if missing
            if not has_return_annotation and args:
                sig_line = func_start
                if 0 <= sig_line < len(modified_lines):
                    line = modified_lines[sig_line]
                    if '-> ' not in line and line.rstrip().endswith(':'):
                        modified_lines[sig_line] = line.rstrip()[:-1] + ' -> Any:'
                        changes.append(f"Added return type annotation to '{func_name}'")

            # Flag high-complexity functions
            if complexity > 10:
                changes.append(
                    f"'{func_name}' complexity={complexy} — consider extracting helpers"
                    if False else
                    f"'{func_name}' complexity={complexity} — consider extracting helpers"
                )

        result = '\n'.join(modified_lines)
        if changes:
            result += "\n\n# Refactoring Notes:\n" + "\n".join(f"# - {c}" for c in changes)

        return CodeResult(
            code=result, language="python",
            changes=changes,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> CodeResult:
        """Safe fallback: return original code if provided, empty otherwise."""
        if isinstance(input_data, dict):
            code = input_data.get("existing_code", "")
            language = input_data.get("language", "python")
        elif hasattr(input_data, "existing_code"):
            code = getattr(input_data, "existing_code", "")
            language = getattr(input_data, "language", "python")
        else:
            code = ""
            language = "python"
        return CodeResult(code=code, language=language, source="fallback")
