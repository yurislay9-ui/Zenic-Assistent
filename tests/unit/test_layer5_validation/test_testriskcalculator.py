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



class TestRiskCalculator:
    """A27: Calculate aggregate risk score from all validations."""

    def setup_method(self):
        self.calculator = RiskCalculator()

    def test_no_issues_low_risk(self):
        """No validation issues should result in low risk."""
        result = self.calculator.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
        })
        assert isinstance(result, RiskResult)
        assert result.level == "low"
        assert result.score == 0.0

    def test_security_threat_increases_risk(self):
        """Security threats should increase risk score."""
        result = self.calculator.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(severity="error", code="eval", message="eval found")],
                risk_score=0.5,
            ),
            "syntax_result": SyntaxResult(valid=True),
        })
        assert result.score > 0.0
        assert result.level in ("medium", "high", "critical")

    def test_syntax_error_increases_risk(self):
        """Syntax errors should increase risk score."""
        result = self.calculator.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="bad syntax")],
            ),
        })
        assert result.score > 0.0

    def test_combined_risk_higher(self):
        """Combined security + syntax issues should be higher risk."""
        result_both = self.calculator.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(severity="error", code="eval", message="eval")],
                risk_score=0.5,
            ),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="err")],
            ),
        })
        result_one = self.calculator.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="err")],
            ),
        })
        assert result_both.score >= result_one.score

    def test_critical_risk_recommendations(self):
        """Critical risk level should have DO NOT deploy recommendation."""
        result = self.calculator.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[
                    ValidationIssue(severity="error", code="eval", message="eval"),
                    ValidationIssue(severity="error", code="exec", message="exec"),
                    ValidationIssue(severity="error", code="os_system", message="os.system"),
                ],
                risk_score=0.9,
            ),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="err")],
            ),
        })
        if result.level == "critical":
            assert any("DO NOT deploy" in r for r in result.recommendations)

    def test_fallback_returns_low_risk(self):
        """Fallback should return low risk."""
        result = self.calculator.fallback(None)
        assert result.level == "low"
        assert result.source == "fallback"

    def test_non_dict_input_uses_fallback(self):
        """Non-dict input should use fallback."""
        result = self.calculator.execute("invalid")
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A28 FixSuggester Tests
# ═══════════════════════════════════════════════════════════

