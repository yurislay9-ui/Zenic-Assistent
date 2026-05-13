"""Tests for fallback classify, extract, and pattern methods."""

import pytest
from src.core.mini_ai_engine import MiniAIEngine, IntentResult
from ._fixtures import engine_no_model


# ================================================================
#  TEST: Fallback Classification
# ================================================================

class TestFallbackClassify:
    """Test keyword-based fallback intent classification."""

    def test_create_spanish(self, engine_no_model):
        result = engine_no_model.classify_intent("crear modulo auth.py")
        assert result.operation == "CREATE"
        assert result.source == "fallback"

    def test_create_english(self, engine_no_model):
        result = engine_no_model.classify_intent("create a new file for authentication")
        assert result.operation == "CREATE"
        assert result.source == "fallback"

    def test_refactor(self, engine_no_model):
        result = engine_no_model.classify_intent("refactorizar login.py")
        assert result.operation == "REFACTOR"
        assert result.source == "fallback"

    def test_delete(self, engine_no_model):
        result = engine_no_model.classify_intent("eliminar archivo viejo.py")
        assert result.operation == "DELETE"
        assert result.source == "fallback"

    def test_search(self, engine_no_model):
        result = engine_no_model.classify_intent("buscar donde se define process_data")
        assert result.operation == "SEARCH"
        assert result.source == "fallback"

    def test_debug(self, engine_no_model):
        result = engine_no_model.classify_intent("corregir bug en validacion")
        assert result.operation == "DEBUG"
        assert result.source == "fallback"

    def test_optimize(self, engine_no_model):
        result = engine_no_model.classify_intent("optimizar la funcion lenta")
        assert result.operation == "OPTIMIZE"
        assert result.source == "fallback"

    def test_explain(self, engine_no_model):
        result = engine_no_model.classify_intent("explicar como funciona el codigo")
        assert result.operation == "EXPLAIN"
        assert result.source == "fallback"

    def test_default_search(self, engine_no_model):
        """Unknown input should default to SEARCH."""
        result = engine_no_model.classify_intent("xyzzy random text")
        assert result.operation in MiniAIEngine.VALID_OPERATIONS
        assert result.source == "fallback"

    def test_goal_bug_fix(self, engine_no_model):
        result = engine_no_model.classify_intent("fix the bug in login")
        assert result.goal == "BUG_FIX"

    def test_goal_feature_add(self, engine_no_model):
        result = engine_no_model.classify_intent("add new feature for auth")
        assert result.goal == "FEATURE_ADD"

    def test_goal_security(self, engine_no_model):
        result = engine_no_model.classify_intent("security vulnerability in auth")
        assert result.goal == "SECURITY_HARDEN"

    def test_goal_performance(self, engine_no_model):
        result = engine_no_model.classify_intent("optimize slow function performance")
        assert result.goal == "PERFORMANCE"


# ================================================================
#  TEST: Fallback Entity Extraction
# ================================================================

class TestFallbackExtract:
    """Test regex-based fallback entity extraction."""

    def test_python_file(self, engine_no_model):
        result = engine_no_model.extract_entities("refactorizar login.py para usar JWT")
        assert result["file"] == "login.py"
        assert result["lang"] == "python"
        assert result["source"] == "fallback"

    def test_kotlin_file(self, engine_no_model):
        result = engine_no_model.extract_entities("crear UserService.kt con coroutines")
        assert result["file"] == "UserService.kt"
        assert result["lang"] == "kotlin"

    def test_go_file(self, engine_no_model):
        result = engine_no_model.extract_entities("optimize handler.go for speed")
        assert result["file"] == "handler.go"
        assert result["lang"] == "go"

    def test_js_file(self, engine_no_model):
        result = engine_no_model.extract_entities("fix bug in app.js")
        assert result["file"] == "app.js"
        assert result["lang"] == "javascript"

    def test_ts_file(self, engine_no_model):
        result = engine_no_model.extract_entities("refactor service.ts")
        assert result["file"] == "service.ts"
        assert result["lang"] == "typescript"

    def test_no_file(self, engine_no_model):
        result = engine_no_model.extract_entities("explain how this works")
        assert result["file"] == ""
        assert result["lang"] == "unknown"

    def test_function_extraction(self, engine_no_model):
        result = engine_no_model.extract_entities("def process_data function is slow")
        assert result["function"] == "process_data"


# ================================================================
#  TEST: Fallback Pattern Suggestion
# ================================================================

class TestFallbackPattern:
    """Test keyword-based fallback pattern suggestion."""

    def test_async_pattern(self, engine_no_model):
        result = engine_no_model.suggest_pattern("handler", "make it async")
        assert result == "async_await_pattern"

    def test_validator_pattern(self, engine_no_model):
        result = engine_no_model.suggest_pattern("input", "validate the data")
        assert result == "validator_pattern"

    def test_security_pattern(self, engine_no_model):
        result = engine_no_model.suggest_pattern("auth_login", "refactor this")
        assert result == "security_pattern"

    def test_cache_pattern(self, engine_no_model):
        result = engine_no_model.suggest_pattern("data", "add cache mechanism")
        assert result == "cache_pattern"

    def test_default_pattern(self, engine_no_model):
        result = engine_no_model.suggest_pattern("generic", "just do something")
        assert result == "default_pattern"
