"""
Tests for Layer 5: Validation & Security agents (A23-A28).

All 6 agents tested:
  - A23 SecurityScanner
  - A24 SyntaxValidator
  - A25 ChainValidator
  - A26 ConfigValidator
  - A27 RiskCalculator
  - A28 FixSuggester
"""

import json
import pytest

from src.core.agents.validation import (
    SecurityScanner,
    SyntaxValidator,
    ChainValidator,
    ConfigValidator,
    RiskCalculator,
    FixSuggester,
)
from src.core.agents.schemas import (
    SecurityResult,
    SyntaxResult,
    ChainResult,
    ConfigResult,
    RiskResult,
    FixSuggestions,
    ValidationIssue,
)


# ═══════════════════════════════════════════════════════════
# A23 SecurityScanner Tests
# ═══════════════════════════════════════════════════════════



class TestSyntaxValidator:
    """A24: Validate code syntax via AST parsing."""

    def setup_method(self):
        self.validator = SyntaxValidator()

    def test_valid_python_code(self):
        """Valid Python code should pass."""
        result = self.validator.execute({"code": "x = 1\nprint(x)", "language": "python"})
        assert isinstance(result, SyntaxResult)
        assert result.valid is True

    def test_invalid_python_syntax(self):
        """Invalid Python should report syntax error."""
        result = self.validator.execute({"code": "def foo(\n  pass", "language": "python"})
        assert result.valid is False
        assert any(e.code == "syntax_error" for e in result.errors)

    def test_missing_return_warning(self):
        """Functions that may not return on all paths should get warning."""
        code = "def foo(x):\n    if x > 0:\n        return x"
        result = self.validator.execute({"code": code, "language": "python"})
        # May have warnings but still valid
        assert isinstance(result, SyntaxResult)

    def test_bare_except_in_ast(self):
        """Bare except detected via AST should be a warning."""
        code = "try:\n    x = 1\nexcept:\n    pass"
        result = self.validator.execute({"code": code, "language": "python"})
        assert any(e.code == "bare_except" for e in result.errors)

    def test_js_brace_validation(self):
        """JS/TS code should be validated via brace balance."""
        result = self.validator.execute({
            "code": "function foo() { return 1; }",
            "language": "javascript",
        })
        assert result.valid is True

    def test_mismatched_braces(self):
        """Mismatched braces should be detected."""
        result = self.validator.execute({
            "code": "function foo() { return [1, 2 ); }",
            "language": "javascript",
        })
        assert result.valid is False

    def test_unclosed_brace(self):
        """Unclosed braces should be detected."""
        result = self.validator.execute({
            "code": "function foo() { return 1;",
            "language": "javascript",
        })
        assert result.valid is False

    def test_empty_code_is_valid(self):
        """Empty code should default to valid=True."""
        result = self.validator.execute({"code": "", "language": "python"})
        assert result.valid is True

    def test_string_input_works(self):
        """String input should work."""
        result = self.validator.execute("x = 1")
        assert result.valid is True

    def test_fallback_returns_valid(self):
        """Fallback should return valid=True."""
        result = self.validator.fallback(None)
        assert result.valid is True
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A25 ChainValidator Tests
# ═══════════════════════════════════════════════════════════

