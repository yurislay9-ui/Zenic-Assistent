"""Tests for ReasoningEngine (Phase 8.1)."""


class TestReasoningEngine:
    """Tests for the ReasoningEngine (Phase 8.1)."""

    def setup_method(self):
        from src.core.reasoning_engine import ReasoningEngine
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_engine_initializes(self):
        """ReasoningEngine should initialize without errors."""
        assert self.engine is not None
        assert self.engine._ai is None
        assert self.engine._semantic is None
        assert self.engine._memory is None

    def test_step_by_step_fallback(self):
        """step_by_step should work with deterministic fallback."""
        result = self.engine.step_by_step("How to create an API?")
        assert result is not None
        assert len(result.answer) > 10
        assert result.confidence > 0.0
        assert len(result.steps) > 0
        assert all(s.source == "fallback" for s in result.steps)

    def test_step_by_step_max_steps(self):
        """step_by_step should respect max_steps parameter."""
        result = self.engine.step_by_step("Test problem", max_steps=2)
        assert len(result.steps) <= 2

    def test_self_reflect_fallback(self):
        """self_reflect should work with deterministic fallback."""
        result = self.engine.self_reflect("Design an auth system")
        assert result is not None
        assert len(result.answer) > 10
        assert result.confidence > 0.0

    def test_self_reflect_iterations(self):
        """self_reflect should limit iterations."""
        result = self.engine.self_reflect("Test", max_iterations=1)
        # Should have at most 2 steps per iteration (generate + evaluate)
        assert len(result.steps) <= 2

    def test_reason_with_context_fallback(self):
        """reason_with_context should work with fallback."""
        result = self.engine.reason_with_context("Build a CRM")
        assert result is not None
        assert len(result.answer) > 10
        assert result.source in ("fallback", "llm")

    def test_reason_auto_simple(self):
        """Auto mode should select step_by_step for simple problems."""
        result = self.engine.reason("simple query")
        assert result is not None
        assert len(result.answer) > 0

    def test_reason_auto_complex(self):
        """Auto mode should select appropriate mode for complex problems."""
        result = self.engine.reason(
            "Build a complete CRM system with API, database, authentication, "
            "notifications and reporting capabilities"
        )
        assert result is not None
        assert result.confidence > 0.0

    def test_reason_explicit_mode(self):
        """Should use explicitly specified mode."""
        result = self.engine.reason("Test", mode="step_by_step")
        from src.core.reasoning_engine import ReasoningMode
        assert result.mode == ReasoningMode.STEP_BY_STEP

    def test_full_fallback_no_model(self):
        """Full fallback should work without any model."""
        from src.core.reasoning_engine import ReasoningMode
        result = self.engine._full_fallback("Any problem")
        assert result.confidence < 0.5
        assert result.mode == ReasoningMode.FALLBACK

    def test_stats(self):
        """Stats should return useful information."""
        self.engine.step_by_step("Test")
        stats = self.engine.stats
        assert "total_calls" in stats
        assert stats["total_calls"] >= 1
        assert "modes" in stats
        assert len(stats["modes"]) == 4

    def test_fallback_step_identifies_api(self):
        """Fallback step 1 should identify API problems."""
        result = self.engine._fallback_step(1, "How to create a REST API endpoint?", [])
        assert "API" in result

    def test_fallback_step_identifies_auth(self):
        """Fallback step 1 should identify auth problems."""
        result = self.engine._fallback_step(1, "Implement login with JWT", [])
        assert "auth" in result.lower() or "authentication" in result.lower()

    def test_fallback_evaluate_short_answer(self):
        """Evaluation should flag short answers."""
        score, issues = self.engine._fallback_evaluate("ok", "test")
        assert score < 0.5
        assert len(issues) > 0

    def test_fallback_evaluate_security_risk(self):
        """Evaluation should flag security risks."""
        score, issues = self.engine._fallback_evaluate("Use eval() to parse input", "parse input")
        assert score < 0.5
        assert any("security" in i.lower() for i in issues)

    def test_estimate_complexity_simple(self):
        """Simple problems should have low complexity."""
        complexity = self.engine._estimate_complexity("create a function")
        assert complexity < 0.5

    def test_estimate_complexity_complex(self):
        """Complex problems should have higher complexity."""
        complexity = self.engine._estimate_complexity(
            "Build a microservice API with database, authentication, "
            "caching, and async pipeline but also webhook integration"
        )
        assert complexity > 0.3

    def test_extract_conclusion_with_marker(self):
        """Should extract conclusion after marker words."""
        result = self.engine._extract_conclusion(
            "Analysis shows the pattern. Therefore, use a factory pattern."
        )
        assert "factory" in result.lower()

    def test_extract_conclusion_without_marker(self):
        """Should return last sentence when no marker found."""
        result = self.engine._extract_conclusion(
            "First approach. Second approach. The best option is to use caching."
        )
        assert len(result) > 5
