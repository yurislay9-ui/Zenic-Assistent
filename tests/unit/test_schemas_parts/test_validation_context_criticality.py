"""
Tests for Validation, Context, and Criticality schemas.
"""

import pytest
from dataclasses import fields

from src.core.agents.schemas import (
    IntentOutput,
    ValidationInput, ValidationIssue, ValidationOutput,
    ContextInput, ContextEntry, ContextOutput,
    CriticalityInput, CriticalityOutput,
)


# ============================================================
#  VALIDATION SCHEMAS
# ============================================================

class TestValidationInput:
    """Tests for ValidationInput schema."""

    def test_default_values(self):
        """Should default to code target with python language."""
        inp = ValidationInput()
        assert inp.target == "code"
        assert inp.content == ""
        assert inp.rules == []
        assert inp.language == "python"


class TestValidationIssue:
    """Tests for ValidationIssue schema."""

    def test_default_values(self):
        """Should default to warning severity."""
        issue = ValidationIssue()
        assert issue.severity == "warning"
        assert issue.code == ""
        assert issue.message == ""
        assert issue.line == 0

    def test_custom_severity(self):
        """Should accept valid severity levels."""
        for sev in ["error", "warning", "info"]:
            issue = ValidationIssue(severity=sev)
            assert issue.severity == sev


class TestValidationOutput:
    """Tests for ValidationOutput schema."""

    def test_default_is_valid(self):
        """Should default to valid with no issues."""
        out = ValidationOutput()
        assert out.is_valid is True
        assert out.issues == []
        assert out.suggestions == []
        assert out.risk_score == 0.0

    def test_with_issues(self):
        """Should accept validation issues."""
        issues = [ValidationIssue(severity="error", message="SQL injection")]
        out = ValidationOutput(is_valid=False, issues=issues, risk_score=0.9)
        assert out.is_valid is False
        assert len(out.issues) == 1
        assert out.issues[0].severity == "error"


# ============================================================
#  CONTEXT SCHEMAS
# ============================================================

class TestContextInput:
    """Tests for ContextInput schema."""

    def test_default_values(self):
        """Should have empty/None defaults."""
        inp = ContextInput()
        assert inp.message == ""
        assert inp.intent_output is None
        assert inp.max_tokens == 500

    def test_with_intent_output(self):
        """Should accept IntentOutput as intent_output."""
        intent = IntentOutput(operation="CREATE")
        inp = ContextInput(message="test", intent_output=intent)
        assert inp.intent_output.operation == "CREATE"


class TestContextEntry:
    """Tests for ContextEntry schema."""

    def test_default_values(self):
        """Should have sensible defaults."""
        entry = ContextEntry()
        assert entry.content == ""
        assert entry.importance == 0.5
        assert entry.recency == 1.0
        assert entry.relevance_score == 0.0

    def test_custom_values(self):
        """Should accept custom relevance and importance."""
        entry = ContextEntry(content="test", importance=0.9, recency=0.3)
        assert entry.importance == 0.9
        assert entry.recency == 0.3


class TestContextOutput:
    """Tests for ContextOutput schema."""

    def test_default_values(self):
        """Should have empty defaults and compression_ratio of 1.0."""
        out = ContextOutput()
        assert out.compressed_context == ""
        assert out.relevant_memories == []
        assert out.entries_used == 0
        assert out.compression_ratio == 1.0
        assert out.source == "fallback"


# ============================================================
#  CRITICALITY SCHEMAS
# ============================================================

class TestCriticalityInput:
    """Tests for CriticalityInput schema."""

    def test_default_values(self):
        """Should have SEARCH/FEATURE_ADD defaults."""
        inp = CriticalityInput()
        assert inp.operation == "SEARCH"
        assert inp.goal == "FEATURE_ADD"
        assert inp.target == ""
        assert inp.context == ""
        assert inp.code_snippet == ""
        assert inp.existing_level is None

    def test_custom_values(self):
        """Should accept custom criticality input."""
        inp = CriticalityInput(
            operation="DELETE", goal="SECURITY_HARDEN",
            target="auth.py", existing_level=2,
        )
        assert inp.operation == "DELETE"
        assert inp.target == "auth.py"
        assert inp.existing_level == 2


class TestCriticalityOutput:
    """Tests for CriticalityOutput schema."""

    def test_default_values(self):
        """Should default to level 2 standard path."""
        out = CriticalityOutput()
        assert out.level == 2
        assert out.path == "standard"
        assert out.confidence == 0.0
        assert out.source == "fallback"
        assert out.adjustments == {}

    def test_critical_level(self):
        """Should accept critical level 3."""
        out = CriticalityOutput(
            level=3, path="high_crit",
            reason="auth module", confidence=0.95,
        )
        assert out.level == 3
        assert out.path == "high_crit"
        assert out.confidence == 0.95

    def test_valid_levels(self):
        """Should accept levels 1, 2, and 3."""
        for level in [1, 2, 3]:
            out = CriticalityOutput(level=level)
            assert out.level == level
