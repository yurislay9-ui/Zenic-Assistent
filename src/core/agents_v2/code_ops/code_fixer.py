"""
A20 CodeFixer — SINGLE RESPONSIBILITY: Fix bugs and errors in code.

Deterministic code fixing: missing colons, bare except, common syntax errors.
No AI. Regex + AST-based pattern fixing for Python, passthrough for others.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import CodeResult


class CodeFixer(BaseAgent[CodeResult]):
    """
    A20: Fix bugs and errors in code.

    Single Responsibility: Code fixing ONLY.
    Method: Regex + AST-based deterministic fixes for Python.
    Fallback: Return original code unchanged.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A20_CodeFixer", **kwargs)

    def execute(self, input_data: Any) -> CodeResult:
        """
        Fix code: apply deterministic bug fixes.

        Input (CodeRequest or dict):
            - existing_code: str
            - language: str

        Output: CodeResult with fixes applied + fixes list.
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
                code="# No existing code provided for fixing\n",
                language=language,
                fixes=["Cannot fix empty code"],
                source="deterministic",
            )

        if language == "python":
            return self._fix_python(code)

        return CodeResult(
            code=code, language=language,
            fixes=["Bug fixing requires LLM for non-Python code"],
            source="deterministic",
        )

    def _fix_python(self, code: str) -> CodeResult:
        """Deterministic Python bug fixes."""
        fixes: list[str] = []
        lines = code.split('\n')
        fixed_lines = list(lines)

        # Fix 1: Missing colons after block statements
        for i, line in enumerate(lines):
            if re.match(r'^\s*(def|if|elif|else|for|while|try|except|finally|with|class)\s', line):
                if not line.rstrip().endswith(':') and not line.rstrip().endswith('\\'):
                    fixed_lines[i] = line.rstrip() + ':'
                    fixes.append(f"Line {i+1}: Added missing ':'")

        # Fix 2: Bare except → except Exception
        for i, line in enumerate(lines):
            if 'except:' in line and 'except Exception:' not in line and 'except BaseException:' not in line:
                fixed_lines[i] = line.replace('except:', 'except Exception:')
                fixes.append(f"Line {i+1}: Changed bare 'except:' to 'except Exception:'")

        # Fix 3: == None → is None
        for i, line in enumerate(fixed_lines):
            if ' == None' in line and ' == NoneType' not in line:
                fixed_lines[i] = line.replace(' == None', ' is None')
                fixes.append(f"Line {i+1}: Changed '== None' to 'is None'")
            if ' != None' in line:
                fixed_lines[i] = fixed_lines[i].replace(' != None', ' is not None')
                fixes.append(f"Line {i+1}: Changed '!= None' to 'is not None'")

        # Fix 4: print without parentheses (Python 2 style)
        for i, line in enumerate(fixed_lines):
            stripped = line.lstrip()
            if stripped.startswith('print ') and not stripped.startswith('print('):
                indent = line[:len(line) - len(stripped)]
                content = stripped[6:].rstrip()
                if not content.startswith('('):
                    fixed_lines[i] = f"{indent}print({content})"
                    fixes.append(f"Line {i+1}: Added parentheses to print()")

        result = '\n'.join(fixed_lines)
        if fixes:
            result += "\n\n# Fixes Applied:\n" + "\n".join(f"# - {f}" for f in fixes)
        else:
            result += "\n\n# No obvious bugs found."

        return CodeResult(
            code=result, language="python",
            fixes=fixes,
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
