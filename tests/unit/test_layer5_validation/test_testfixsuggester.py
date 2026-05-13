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

from src.core.agents_v2.validation import (
    SecurityScanner,
    SyntaxValidator,
    ChainValidator,
    ConfigValidator,
    RiskCalculator,
    FixSuggester,
)
from src.core.agents_v2.schemas import (
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



class TestFixSuggester:
    """A28: Suggest fixes for validation issues."""

    def setup_method(self):
        self.suggester = FixSuggester()

    def test_no_issues_empty_suggestions(self):
        """No issues should return empty suggestions."""
        result = self.suggester.execute([])
        assert isinstance(result, FixSuggestions)
        assert len(result.suggestions) == 0

    def test_eval_fix_suggestion(self):
        """eval() should get ast.literal_eval() suggestion."""
        issues = [ValidationIssue(severity="error", code="dangerous_eval", message="eval found")]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 1
        assert "ast.literal_eval" in result.suggestions[0]
        assert result.priorities[0] == "high"

    def test_warning_is_medium_priority(self):
        """Warning severity should be medium priority."""
        issues = [ValidationIssue(severity="warning", code="missing_return", message="no return")]
        result = self.suggester.execute(issues)
        assert result.priorities[0] == "medium"

    def test_info_is_low_priority(self):
        """Info severity should be low priority."""
        issues = [ValidationIssue(severity="info", code="todo_comment", message="TODO found")]
        result = self.suggester.execute(issues)
        assert result.priorities[0] == "low"

    def test_auto_fixable_codes(self):
        """Known auto-fixable codes should be listed."""
        issues = [
            ValidationIssue(severity="warning", code="bare_except", message="bare except"),
            ValidationIssue(severity="warning", code="yaml_unsafe", message="unsafe yaml"),
        ]
        result = self.suggester.execute(issues)
        assert "bare_except" in result.auto_fixable
        assert "yaml_unsafe" in result.auto_fixable

    def test_dict_input_with_issues_key(self):
        """Dict input with 'issues' key should work."""
        issues = [ValidationIssue(severity="error", code="dangerous_eval", message="eval")]
        result = self.suggester.execute({"issues": issues})
        assert len(result.suggestions) == 1

    def test_unknown_code_gets_generic_suggestion(self):
        """Unknown error code should get a generic suggestion."""
        issues = [ValidationIssue(severity="error", code="unknown_error", message="something bad")]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 1
        assert "Review and fix" in result.suggestions[0]

    def test_multiple_issues(self):
        """Multiple issues should all get suggestions."""
        issues = [
            ValidationIssue(severity="error", code="dangerous_eval", message="eval"),
            ValidationIssue(severity="warning", code="bare_except", message="bare except"),
            ValidationIssue(severity="info", code="debug_enabled", message="debug on"),
        ]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 3
        assert len(result.priorities) == 3

    def test_fallback_returns_empty(self):
        """Fallback should return empty suggestions."""
        result = self.suggester.fallback(None)
        assert len(result.suggestions) == 0
        assert result.source == "fallback"

    def test_non_validation_issue_skipped(self):
        """Non-ValidationIssue objects should be skipped."""
        issues = [
            "not an issue object",
            ValidationIssue(severity="error", code="dangerous_eval", message="eval"),
        ]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 1  # Only the valid issue


# ═══════════════════════════════════════════════════════════
# Integration: Full Validation Pipeline Test
# ═══════════════════════════════════════════════════════════

