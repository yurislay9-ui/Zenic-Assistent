"""Tests for auto mode selection, fallback methods, confidence/complexity, stats, extract conclusion."""

import pytest
from unittest.mock import MagicMock

from src.core.reasoning_engine import (
    ReasoningEngine,
    ReasoningMode,
    ReasoningStep,
    ReasoningResult,
    MAX_REASONING_STEPS,
    MAX_REFLECT_ITERATIONS,
    MIN_CONFIDENCE_ACCEPT,
)


# ============================================================
#  AUTO MODE SELECTION TESTS
# ============================================================

class TestAutoModeSelection:
    """Tests for ReasoningEngine.reason() auto mode."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_auto_simple_problem(self):
        result = self.engine.reason("create a function")
        assert result.mode == ReasoningMode.FALLBACK

    def test_explicit_mode(self):
        result = self.engine.reason("Test", mode="step_by_step")
        assert result.mode == ReasoningMode.STEP_BY_STEP

    def test_explicit_self_reflect_mode(self):
        result = self.engine.reason("Test", mode="self_reflect")
        assert result.mode == ReasoningMode.SELF_REFLECT

    def test_explicit_with_context_mode(self):
        result = self.engine.reason("Test", mode="with_context")
        assert result.mode == ReasoningMode.WITH_CONTEXT


# ============================================================
#  FALLBACK METHOD TESTS
# ============================================================

class TestFallbackMethods:
    """Tests for ReasoningEngine fallback methods."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_fallback_step_api(self):
        result = self.engine._fallback_step(1, "How to create a REST API endpoint?", [])
        assert "API" in result

    def test_fallback_step_auth(self):
        result = self.engine._fallback_step(1, "Implement login with JWT", [])
        assert "auth" in result.lower() or "authentication" in result.lower()

    def test_fallback_step_database(self):
        result = self.engine._fallback_step(1, "Design the database schema", [])
        assert "data" in result.lower()

    def test_fallback_step_2(self):
        result = self.engine._fallback_step(2, "any problem", [])
        assert "pattern" in result.lower() or "standard" in result.lower()

    def test_fallback_generate_api(self):
        result = self.engine._fallback_generate("create an API", 1)
        assert "API" in result or "api" in result.lower()

    def test_fallback_evaluate_short_answer(self):
        score, issues = self.engine._fallback_evaluate("ok", "test")
        assert score < 0.5
        assert len(issues) > 0

    def test_fallback_evaluate_security_risk(self):
        score, issues = self.engine._fallback_evaluate("Use eval() to parse", "test")
        assert any("security" in i.lower() for i in issues)

    def test_full_fallback(self):
        result = self.engine._full_fallback("any problem")
        assert result.mode == ReasoningMode.FALLBACK
        assert result.confidence < 0.5
        assert len(result.steps) > 0

    def test_fallback_context_reasoning(self):
        result = self.engine._fallback_context_reasoning(
            "test", {"operation": "CREATE", "goal": "FEATURE_ADD"}
        )
        assert "CREATE" in result or "feature_add" in result.lower()


# ============================================================
#  CONFIDENCE & COMPLEXITY TESTS
# ============================================================

class TestConfidenceAndComplexity:
    """Tests for confidence estimation and complexity estimation."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_estimate_confidence_increases_with_length(self):
        short = self.engine._estimate_confidence("ok", 1, 3)
        long = self.engine._estimate_confidence(
            "This is a very detailed and comprehensive answer that provides thorough analysis.",
            1, 3,
        )
        assert long >= short

    def test_estimate_confidence_hedging_reduces(self):
        certain = self.engine._estimate_confidence(
            "The answer is clearly 42.", 1, 3
        )
        hedges = self.engine._estimate_confidence(
            "Maybe perhaps the answer might possibly be 42.", 1, 3
        )
        assert certain > hedges

    def test_estimate_complexity_simple(self):
        complexity = self.engine._estimate_complexity("create a function")
        assert complexity < 0.5

    def test_estimate_complexity_complex(self):
        complexity = self.engine._estimate_complexity(
            "Build a microservice API with database, authentication, "
            "caching, and async pipeline but also webhook integration"
        )
        assert complexity > 0.3

    def test_estimate_complexity_tech_terms(self):
        c1 = self.engine._estimate_complexity("make a thing")
        c2 = self.engine._estimate_complexity("make an API with database and webhook")
        assert c2 > c1


# ============================================================
#  STATS TESTS
# ============================================================

class TestReasoningStats:
    """Tests for ReasoningEngine.stats property."""

    def test_stats_structure(self):
        engine = ReasoningEngine()
        stats = engine.stats
        assert "total_calls" in stats
        assert "total_time_s" in stats
        assert "ai_available" in stats
        assert "semantic_available" in stats
        assert "memory_available" in stats
        assert "modes" in stats

    def test_stats_increments_calls(self):
        engine = ReasoningEngine()
        engine.step_by_step("Test")
        assert engine.stats["total_calls"] >= 1

    def test_stats_reports_availability(self):
        engine = ReasoningEngine()
        stats = engine.stats
        assert stats["ai_available"] is False
        assert stats["semantic_available"] is False
        assert stats["memory_available"] is False


# ============================================================
#  EXTRACT CONCLUSION TESTS
# ============================================================

class TestExtractConclusion:
    """Tests for _extract_conclusion helper."""

    def setup_method(self):
        self.engine = ReasoningEngine()

    def test_with_therefore(self):
        result = self.engine._extract_conclusion(
            "Analysis shows the pattern. Therefore, use a factory pattern."
        )
        assert "factory" in result.lower()

    def test_with_conclusion_marker(self):
        result = self.engine._extract_conclusion(
            "Some analysis. Conclusion: the answer is 42"
        )
        assert "42" in result or "answer" in result.lower()

    def test_without_marker(self):
        result = self.engine._extract_conclusion(
            "First approach. Second approach. The best option is to use caching."
        )
        assert len(result) > 5

    def test_empty_text(self):
        result = self.engine._extract_conclusion("")
        assert isinstance(result, str)
