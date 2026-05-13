"""
Unit tests for Code Transformer

Tests refactoring, fixing, and optimization transformations.
"""

import pytest
from src.core.code_transformer import CodeTransformer


PYTHON_CODE = '''
def slow_function(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result

class OldStyleClass:
    def __init__(self, value):
        self.value = value
'''


@pytest.fixture
def transformer():
    return CodeTransformer()


class TestCodeTransformer:
    """Tests for the CodeTransformer class."""

    def test_optimize_function_returns_string(self, transformer):
        """Should return a string snippet for the optimized function."""
        result = transformer.optimize_function("slow_function", "python")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_refactor_python_returns_string(self, transformer):
        """Should return refactored Python code."""
        ast_analysis = {"functions": 1, "classes": 1, "max_complexity": 3,
                        "function_names": ["slow_function"],
                        "class_names": ["OldStyleClass"]}
        result = transformer.refactor_python(PYTHON_CODE, ast_analysis)
        assert isinstance(result, str)

    def test_fix_python_returns_string(self, transformer):
        """Should return fixed Python code."""
        ast_analysis = {"functions": 1, "classes": 1, "max_complexity": 3,
                        "function_names": ["slow_function"],
                        "class_names": ["OldStyleClass"]}
        result = transformer.fix_python(PYTHON_CODE, ast_analysis)
        assert isinstance(result, str)

    def test_optimize_with_solver_insights(self, transformer):
        """Should incorporate solver insights into optimization."""
        solver_insights = {"status": "PROVEN", "critical_target": True,
                          "validated_constraints": ["null_safety"]}
        result = transformer.optimize_function(
            "auth_check", "python",
            ast_analysis={"functions": 1, "max_complexity": 5,
                         "function_names": ["auth_check"], "class_names": []},
            solver_insights=solver_insights
        )
        assert isinstance(result, str)

    def test_optimize_different_languages(self, transformer):
        """Should handle different language targets."""
        for lang in ["python", "kotlin", "go", "javascript"]:
            result = transformer.optimize_function("target_func", lang)
            assert isinstance(result, str)
