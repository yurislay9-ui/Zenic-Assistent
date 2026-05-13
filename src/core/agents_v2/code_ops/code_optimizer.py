"""
A19 CodeOptimizer — SINGLE RESPONSIBILITY: Optimize code for performance.

Deterministic optimization: detect bare except, open() without with, anti-patterns.
No AI. AST-based pattern detection for Python, passthrough for others.
"""

from __future__ import annotations

import ast
from typing import Any

from ..resilience import BaseAgent
from ..schemas import CodeResult


class CodeOptimizer(BaseAgent[CodeResult]):
    """
    A19: Optimize code for performance.

    Single Responsibility: Code optimization ONLY.
    Method: AST-based anti-pattern detection + optimization notes.
    Fallback: Return original code unchanged.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A19_CodeOptimizer", **kwargs)

    def execute(self, input_data: Any) -> CodeResult:
        """
        Optimize code: detect anti-patterns, suggest improvements.

        Input (CodeRequest or dict):
            - existing_code: str
            - language: str

        Output: CodeResult with optimization notes.
        """
        if hasattr(input_data, "existing_code"):
            code = getattr(input_data, "existing_code", "")
            language = getattr(input_data, "language", "python")
        elif isinstance(input_data, dict):
            code = input_data.get("existing_code", "")
            language = input_data.get("language", "python")
        else:
            code = str(input_data)
            language = "python"

        if not code:
            return CodeResult(
                code="# No existing code provided for optimization\n",
                language=language,
                improvements=["Cannot optimize empty code"],
                source="deterministic",
            )

        if language == "python":
            return self._optimize_python(code)

        return CodeResult(
            code=code, language=language,
            improvements=["Optimization requires LLM for non-Python code"],
            source="deterministic",
        )

    def _optimize_python(self, code: str) -> CodeResult:
        """AST-based deterministic Python optimization."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return CodeResult(
                code=code, language="python",
                improvements=["Cannot parse code — returning original"],
                source="deterministic",
            )

        improvements: list[str] = []

        # Check for bare except
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                improvements.append("Bare 'except:' found — replace with 'except Exception:'")

        # Check for open() without with
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = getattr(node, 'func', None)
                if isinstance(func, ast.Name) and func.id == 'open':
                    improvements.append("open() without 'with' — potential resource leak")

        # Check for string concatenation in loops
        for node in ast.walk(tree):
            if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
                if isinstance(node.target, ast.Name):
                    for parent in ast.walk(tree):
                        if isinstance(parent, (ast.For, ast.While)):
                            improvements.append(
                                f"String concatenation in loop (+= on '{node.target.id}') — use list.append() + join()"
                            )
                            break

        # Check for mutable default arguments
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        improvements.append(
                            f"Mutable default argument in '{node.name}' — use None and initialize in body"
                        )

        if improvements:
            notes = "\n".join(f"# - {i}" for i in improvements)
            result_code = code + f"\n\n# Optimization Notes:\n{notes}"
        else:
            result_code = code
            improvements.append("No obvious optimizations found")

        return CodeResult(
            code=result_code, language="python",
            improvements=improvements,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> CodeResult:
        """Safe fallback: return original code."""
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
