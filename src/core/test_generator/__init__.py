"""
TestGenerator — Auto-generate pytest tests for generated code.

Problem: Generated code is never tested. Users don't know if the
CRUD service, auth module, or API endpoints actually work.

Solution: TestGenerator analyzes generated code (AST) and produces
comprehensive pytest test files that:
  1. Test all public methods
  2. Test CRUD operations with real SQLite (in-memory)
  3. Test auth flows (hash, verify, token, login)
  4. Test API endpoints via TestClient
  5. Test edge cases (empty input, None, invalid types)
  6. Generate fixtures for test data

M9 Implementation: Pure Python, no external APIs. Uses ast module.
"""

import ast
import logging
from typing import List, Dict

from ._helpers import (
    TYPE_FIXTURES,
    generate_syntax_error_tests,
    generate_minimal_tests,
)
from ._analysis_mixin import ASTAnalysisMixin
from ._codegen_mixin import CodeGenMixin

logger = logging.getLogger(__name__)

__all__ = ["TestGenerator"]


class TestGenerator(ASTAnalysisMixin, CodeGenMixin):
    """Auto-generate pytest test files from Python source code."""

    def generate_tests(self, code: str, module_name: str = "module",
                        project_name: str = "test_project") -> str:
        """Generate a complete pytest test file from source code.

        Args:
            code: Python source code to generate tests for
            module_name: Name of the module being tested
            project_name: Project name for imports

        Returns:
            Complete pytest test file as a string
        """
        # Parse the source code
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return generate_syntax_error_tests(module_name, e)

        # Analyze the AST
        classes = self._extract_classes(tree)
        functions = self._extract_functions(tree)

        if not classes and not functions:
            return generate_minimal_tests(module_name)

        # Generate test file
        parts = [
            self._generate_header(module_name, project_name),
            self._generate_imports(module_name, classes),
            self._generate_fixtures(classes),
        ]

        # Generate test classes
        for cls_info in classes:
            parts.append(self._generate_class_tests(cls_info, module_name))

        # Generate function tests
        for fn_info in functions:
            parts.append(self._generate_function_tests(fn_info, module_name))

        return '\n\n'.join(parts) + '\n'
