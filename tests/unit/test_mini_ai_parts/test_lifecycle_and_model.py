"""Tests for template gaps, pattern generation, violation, subtask, lifecycle, parsing, IntentResult, and with-model."""

import pytest
from unittest.mock import MagicMock
from src.core.mini_ai_engine import MiniAIEngine, IntentResult
from ._fixtures import engine_no_model, engine_with_model


# ================================================================
#  TEST: Fallback Template Gap Filling
# ================================================================

class TestFallbackTemplateGaps:
    """Test template gap filling with defaults."""

    def test_no_gaps(self, engine_no_model):
        template = "def hello(): pass"
        result = engine_no_model.fill_template_gaps(template, {})
        assert result == template

    def test_fill_from_context(self, engine_no_model):
        template = "def __GAP_FUNC_NAME__(): pass"
        result = engine_no_model.fill_template_gaps(template, {"func_name": "process"})
        assert "process" in result
        assert "__GAP_" not in result

    def test_fill_with_defaults(self, engine_no_model):
        template = "class __GAP_CLASS_NAME__: pass"
        result = engine_no_model.fill_template_gaps(template, {})
        assert "__GAP_" not in result
        assert "GeneratedClass" in result

    def test_fill_multiple_gaps(self, engine_no_model):
        template = "def __GAP_FUNC_NAME__(__GAP_PARAMS__) -> __GAP_RETURN_TYPE__:\n    __GAP_BODY__"
        result = engine_no_model.fill_template_gaps(template, {"func_name": "calculate"})
        assert "__GAP_" not in result
        assert "calculate" in result


# ================================================================
#  TEST: Fallback Pattern Generation
# ================================================================

class TestFallbackPatternGeneration:
    """Test hardcoded pattern snippet generation."""

    def test_async_await_python(self, engine_no_model):
        result = engine_no_model.generate_pattern("async_await", "python")
        assert "async def" in result
        assert "await" in result

    def test_validator_python(self, engine_no_model):
        result = engine_no_model.generate_pattern("validator", "python")
        assert "def validate" in result

    def test_security_python(self, engine_no_model):
        result = engine_no_model.generate_pattern("security", "python")
        assert "hashlib" in result or "secrets" in result

    def test_cache_python(self, engine_no_model):
        result = engine_no_model.generate_pattern("cache", "python")
        assert "cache" in result.lower() or "lru_cache" in result

    def test_default_python(self, engine_no_model):
        result = engine_no_model.generate_pattern("unknown_pattern", "python")
        assert len(result) > 0

    def test_kotlin_default(self, engine_no_model):
        result = engine_no_model.generate_pattern("something", "kotlin")
        assert "fun " in result

    def test_go_default(self, engine_no_model):
        result = engine_no_model.generate_pattern("something", "go")
        assert "func " in result

    def test_javascript_default(self, engine_no_model):
        result = engine_no_model.generate_pattern("something", "javascript")
        assert "function" in result


# ================================================================
#  TEST: Fallback Violation Explanation
# ================================================================

class TestFallbackViolationExplanation:
    """Test fallback violation explanation."""

    def test_no_violations(self, engine_no_model):
        result = engine_no_model.explain_violation("x = 1", [])
        assert "No violations" in result

    def test_with_violations(self, engine_no_model):
        result = engine_no_model.explain_violation("x = 1/0", ["division_by_zero"])
        assert "division_by_zero" in result

    def test_multiple_violations(self, engine_no_model):
        result = engine_no_model.explain_violation("code", ["bug1", "bug2", "bug3"])
        assert "bug1" in result


# ================================================================
#  TEST: Fallback Subtask Description
# ================================================================

class TestFallbackSubtaskDescription:
    """Test fallback subtask name generation."""

    def test_basic(self, engine_no_model):
        result = engine_no_model.describe_subtask("auth_handler", "REPLACE")
        assert "replace" in result
        assert "auth_handler" in result

    def test_with_context(self, engine_no_model):
        result = engine_no_model.describe_subtask("login", "DELETE", "security module")
        assert "delete" in result
        assert "login" in result


# ================================================================
#  TEST: Engine Lifecycle
# ================================================================

class TestEngineLifecycle:
    """Test model loading, unloading, stats."""

    def test_no_model_by_default(self, engine_no_model):
        assert not engine_no_model.is_loaded

    def test_stats_no_model(self, engine_no_model):
        stats = engine_no_model.stats
        assert stats["model_loaded"] is False
        assert stats["total_calls"] == 0

    def test_load_nonexistent_model(self):
        engine = MiniAIEngine(model_path="/nonexistent/model.gguf", auto_load=False)
        result = engine.load_model()
        assert result is False
        assert not engine.is_loaded

    def test_unload_when_not_loaded(self, engine_no_model):
        engine_no_model.unload_model()
        assert not engine_no_model.is_loaded

    def test_call_count_increases(self, engine_no_model):
        stats = engine_no_model.stats
        assert "total_calls" in stats
        assert "fallback_rate" in stats


# ================================================================
#  TEST: Response Parsing
# ================================================================

class TestResponseParsing:
    """Test Qwen3 think-block extraction."""

    def test_extract_from_think_block(self):
        raw = "<think\nOkay let me think about this\n</think\n>\n\nCREATE"
        result = MiniAIEngine._extract_answer(raw)
        assert result == "CREATE"

    def test_extract_no_think(self):
        raw = "REFACTOR"
        result = MiniAIEngine._extract_answer(raw)
        assert result == "REFACTOR"

    def test_extract_with_code_fence(self):
        raw = '<think\nthinking\n</think\n>\n\n```json\n{"file": "test.py"}\n```'
        result = MiniAIEngine._extract_answer(raw)
        assert "test.py" in result or "file" in result
        assert "```" not in result

    def test_extract_empty_think(self):
        raw = "<think\n</think\n>\n\nOPTIMIZE"
        result = MiniAIEngine._extract_answer(raw)
        assert result == "OPTIMIZE"


# ================================================================
#  TEST: IntentResult Dataclass
# ================================================================

class TestIntentResult:
    """Test IntentResult dataclass."""

    def test_defaults(self):
        result = IntentResult()
        assert result.operation == "SEARCH"
        assert result.goal == "FEATURE_ADD"
        assert result.confidence == 0.0
        assert result.source == "fallback"

    def test_with_values(self):
        result = IntentResult(operation="CREATE", goal="FEATURE_ADD", confidence=0.75, source="llm")
        assert result.operation == "CREATE"
        assert result.source == "llm"


# ================================================================
#  TEST: With Model (if available)
# ================================================================

class TestWithModel:
    """Tests that require the model to be loaded. Skip if model not available."""

    def test_model_loads(self, engine_with_model):
        assert engine_with_model.is_loaded

    def test_classify_intent_llm(self, engine_with_model):
        result = engine_with_model.classify_intent("crear modulo auth.py")
        assert result.operation in MiniAIEngine.VALID_OPERATIONS
        assert result.source in ("llm", "fallback")

    def test_extract_entities_llm(self, engine_with_model):
        result = engine_with_model.extract_entities("refactorizar UserService.kt para usar coroutines")
        assert "file" in result
        assert "lang" in result

    def test_suggest_pattern_llm(self, engine_with_model):
        result = engine_with_model.suggest_pattern("auth_handler", "make it more secure")
        assert len(result) > 0

    def test_explain_violation_llm(self, engine_with_model):
        result = engine_with_model.explain_violation("x = 1/0", ["division_by_zero"])
        assert len(result) > 0

    def test_describe_subtask_llm(self, engine_with_model):
        result = engine_with_model.describe_subtask("auth", "REPLACE", "security module")
        assert len(result) > 0

    def test_stats_after_calls(self, engine_with_model):
        engine_with_model.classify_intent("test")
        stats = engine_with_model.stats
        assert stats["total_calls"] >= 1

    def test_unload_and_reload(self, engine_with_model):
        assert engine_with_model.is_loaded
        engine_with_model.unload_model()
        assert not engine_with_model.is_loaded
        result = engine_with_model.load_model()
        assert result is True
        assert engine_with_model.is_loaded
