"""Tests for init, step-by-step, self-reflect, and reason-with-context."""

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
#  INITIALIZATION TESTS
# ============================================================

class TestReasoningEngineInit:
    """Tests for ReasoningEngine initialization."""

    def test_init_no_dependencies(self):
        engine = ReasoningEngine()
        assert engine._ai is None
        assert engine._semantic is None
        assert engine._memory is None
        assert engine._call_count == 0
        assert engine._total_time == 0.0

    def test_init_with_mock_ai(self):
        mock_ai = MagicMock()
        engine = ReasoningEngine(mini_ai=mock_ai)
        assert engine._ai is mock_ai

    def test_init_with_all_layers(self):
        mock_ai = MagicMock()
        mock_semantic = MagicMock()
        mock_memory = MagicMock()
        engine = ReasoningEngine(
            mini_ai=mock_ai,
            semantic_engine=mock_semantic,
            smart_memory=mock_memory,
        )
        assert engine._ai is mock_ai
        assert engine._semantic is mock_semantic
        assert engine._memory is mock_memory


# ============================================================
#  STEP-BY-STEP REASONING TESTS
# ============================================================

class TestStepByStep:
    """Tests for ReasoningEngine.step_by_step()."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_produces_result(self):
        result = self.engine.step_by_step("How to create an API?")
        assert isinstance(result, ReasoningResult)
        assert len(result.answer) > 10
        assert result.confidence > 0.0

    def test_correct_mode(self):
        result = self.engine.step_by_step("Test problem")
        assert result.mode == ReasoningMode.STEP_BY_STEP

    def test_steps_count_respected(self):
        result = self.engine.step_by_step("Test", max_steps=2)
        assert len(result.steps) <= 2

    def test_default_steps_count(self):
        result = self.engine.step_by_step("Test", max_steps=MAX_REASONING_STEPS)
        assert len(result.steps) <= MAX_REASONING_STEPS

    def test_fallback_source_when_no_ai(self):
        result = self.engine.step_by_step("Test")
        assert all(s.source == "fallback" for s in result.steps)

    def test_context_appended(self):
        result = self.engine.step_by_step("Test", context="Some context")
        assert result is not None

    def test_with_mock_ai(self):
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "The answer is to use FastAPI."
        engine = ReasoningEngine(mini_ai=mock_ai)
        result = engine.step_by_step("How to build API?")
        assert any(s.source == "llm" for s in result.steps)


# ============================================================
#  SELF-REFLECT REASONING TESTS
# ============================================================

class TestSelfReflect:
    """Tests for ReasoningEngine.self_reflect()."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_produces_result(self):
        result = self.engine.self_reflect("Design an auth system")
        assert isinstance(result, ReasoningResult)
        assert len(result.answer) > 10

    def test_correct_mode(self):
        result = self.engine.self_reflect("Test")
        assert result.mode == ReasoningMode.SELF_REFLECT

    def test_iterations_limited(self):
        result = self.engine.self_reflect("Test", max_iterations=1)
        assert len(result.steps) <= 2

    def test_with_mock_ai_high_score(self):
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.side_effect = [
            "Use JWT tokens for auth.",
            '{"score": 0.9, "issues": [], "missing": []}',
        ]
        engine = ReasoningEngine(mini_ai=mock_ai)
        result = engine.self_reflect("Auth system")
        assert result.confidence >= 0.7


# ============================================================
#  REASON WITH CONTEXT TESTS
# ============================================================

class TestReasonWithContext:
    """Tests for ReasoningEngine.reason_with_context()."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_produces_result(self):
        result = self.engine.reason_with_context("Build a CRM")
        assert isinstance(result, ReasoningResult)
        assert len(result.answer) > 10

    def test_correct_mode(self):
        result = self.engine.reason_with_context("Test")
        assert result.mode == ReasoningMode.WITH_CONTEXT

    def test_with_semantic_engine(self):
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        mock_result = MagicMock()
        mock_result.source = "embedding"
        mock_result.confidence = 0.8
        mock_result.operation = "CREATE"
        mock_result.goal = "FEATURE_ADD"
        mock_semantic.classify_intent.return_value = mock_result
        engine = ReasoningEngine(semantic_engine=mock_semantic)
        result = engine.reason_with_context("Build a CRM system")
        assert result.context_used is True

    def test_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.get_working_context.return_value = "Previous work on CRM"
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        mock_result = MagicMock()
        mock_result.source = "embedding"
        mock_result.confidence = 0.8
        mock_result.operation = "CREATE"
        mock_result.goal = "FEATURE_ADD"
        mock_semantic.classify_intent.return_value = mock_result
        mock_memory.find_similar_solutions.return_value = []
        engine = ReasoningEngine(semantic_engine=mock_semantic, smart_memory=mock_memory)
        result = engine.reason_with_context("Build CRM")
        assert result is not None
