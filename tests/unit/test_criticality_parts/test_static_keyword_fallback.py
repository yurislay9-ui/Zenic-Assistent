"""
Tests for CriticalityAgent static methods, keyword signal, and fallback fusion.
"""

import pytest

from src.core.agents.criticality_agent import (
    CriticalityAgent,
    LEVEL_FAST,
    LEVEL_MODERATE,
    LEVEL_SURGICAL,
)
from src.core.agents.schemas import CriticalityInput


# ============================================================
#  Test: Static Utility Methods
# ============================================================

class TestCriticalityStaticMethods:
    """Tests for static utility methods."""

    def test_normalize_none(self):
        """Should return LEVEL_MODERATE for None."""
        assert CriticalityAgent.normalize_criticality(None) == LEVEL_MODERATE

    def test_normalize_int(self):
        """Should pass through valid int values."""
        assert CriticalityAgent.normalize_criticality(1) == 1
        assert CriticalityAgent.normalize_criticality(2) == 2
        assert CriticalityAgent.normalize_criticality(3) == 3

    def test_normalize_int_clamped(self):
        """Should clamp int values to 1-3 range."""
        assert CriticalityAgent.normalize_criticality(0) == 1
        assert CriticalityAgent.normalize_criticality(5) == 3
        assert CriticalityAgent.normalize_criticality(-1) == 1

    def test_normalize_string_standard(self):
        """Should normalize 'standard' to 1."""
        assert CriticalityAgent.normalize_criticality("standard") == 1
        assert CriticalityAgent.normalize_criticality("fast") == 1
        assert CriticalityAgent.normalize_criticality("low") == 1

    def test_normalize_string_moderate(self):
        """Should normalize 'moderate' to 2."""
        assert CriticalityAgent.normalize_criticality("moderate") == 2
        assert CriticalityAgent.normalize_criticality("deep") == 2
        assert CriticalityAgent.normalize_criticality("medium") == 2

    def test_normalize_string_critical(self):
        """Should normalize 'critical' to 3."""
        assert CriticalityAgent.normalize_criticality("critical") == 3
        assert CriticalityAgent.normalize_criticality("surgical") == 3
        assert CriticalityAgent.normalize_criticality("high") == 3

    def test_normalize_canonical_names(self):
        """Should normalize canonical FAST_STANDARD, DEEP_MODERATE, SURGICAL_CRITICAL."""
        assert CriticalityAgent.normalize_criticality("fast_standard") == 1
        assert CriticalityAgent.normalize_criticality("deep_moderate") == 2
        assert CriticalityAgent.normalize_criticality("surgical_critical") == 3

    def test_normalize_string_digit(self):
        """Should normalize string digits."""
        assert CriticalityAgent.normalize_criticality("1") == 1
        assert CriticalityAgent.normalize_criticality("2") == 2
        assert CriticalityAgent.normalize_criticality("3") == 3

    def test_normalize_unknown_defaults_moderate(self):
        """Should default to moderate for unknown values."""
        assert CriticalityAgent.normalize_criticality("unknown") == LEVEL_MODERATE

    def test_level_to_path(self):
        """Should map levels to DAG paths."""
        assert CriticalityAgent.level_to_path(1) == "low_crit"
        assert CriticalityAgent.level_to_path(2) == "standard"
        assert CriticalityAgent.level_to_path(3) == "high_crit"


# ============================================================
#  Test: Keyword Signal
# ============================================================

class TestCriticalityKeywordSignal:
    """Tests for _keyword_signal() analysis."""

    def test_multiple_critical_keywords_surgical(self, agent):
        """Should return SURGICAL for 2+ critical keyword hits."""
        level = agent._keyword_signal("auth token module")
        assert level == LEVEL_SURGICAL

    def test_single_critical_keyword_moderate(self, agent):
        """Should return MODERATE for 1 critical keyword hit."""
        level = agent._keyword_signal("auth module")
        assert level == LEVEL_MODERATE

    def test_multiple_moderate_keywords_moderate(self, agent):
        """Should return MODERATE for 2+ moderate keyword hits."""
        level = agent._keyword_signal("api endpoint handler")
        assert level == LEVEL_MODERATE

    def test_no_keywords_fast(self, agent):
        """Should return FAST for no keyword hits."""
        level = agent._keyword_signal("simple utility function")
        assert level == LEVEL_FAST


# ============================================================
#  Test: Fallback Multi-Signal Fusion
# ============================================================

class TestCriticalityFallback:
    """Tests for deterministic multi-signal fusion fallback."""

    def test_critical_target_elevates(self, agent):
        """Should elevate criticality for critical targets (auth, payment)."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
            target="auth.py",
            context="implement login",
        ))
        assert result.level >= LEVEL_MODERATE
        assert result.source == "fallback"

    def test_delete_operation_elevates(self, agent):
        """Should elevate criticality for DELETE operations."""
        result = agent.fallback(CriticalityInput(
            operation="DELETE",
            goal="FEATURE_ADD",
            target="user_handler.py",
        ))
        assert result.level >= LEVEL_MODERATE

    def test_safe_search_stays_fast(self, agent):
        """Should stay FAST for safe SEARCH + READABILITY."""
        result = agent.fallback(CriticalityInput(
            operation="SEARCH",
            goal="READABILITY",
            target="utils.py",
        ))
        assert result.level == LEVEL_FAST

    def test_security_harden_elevates(self, agent):
        """Should elevate for SECURITY_HARDEN goal."""
        result = agent.fallback(CriticalityInput(
            operation="REFACTOR",
            goal="SECURITY_HARDEN",
            target="auth.py",
        ))
        assert result.level >= LEVEL_MODERATE

    def test_existing_level_not_lowered(self, agent):
        """Should not lower criticality below existing_level."""
        result = agent.fallback(CriticalityInput(
            operation="SEARCH",
            goal="READABILITY",
            target="utils.py",
            existing_level=3,
        ))
        assert result.level >= 3

    def test_result_has_path(self, agent):
        """Should include DAG path in result."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
        ))
        assert result.path in ["low_crit", "standard", "high_crit"]

    def test_result_has_reason(self, agent):
        """Should include explanatory reason in result."""
        result = agent.fallback(CriticalityInput(
            operation="DELETE",
            goal="SECURITY_HARDEN",
        ))
        assert result.reason != ""

    def test_result_has_confidence(self, agent):
        """Should include confidence score in result."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
        ))
        assert 0.0 <= result.confidence <= 1.0

    def test_result_has_adjustments(self, agent):
        """Should include behavioral adjustments in result."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
        ))
        assert isinstance(result.adjustments, dict)
        assert "code_agent" in result.adjustments
        assert "business_agent" in result.adjustments
