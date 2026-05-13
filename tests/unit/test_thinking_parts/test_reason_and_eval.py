"""Tests for reason, evaluate_code, decompose, architecture, chain_of_thought, stats."""

import os
import pytest
from unittest.mock import MagicMock, patch

import src.core.thinking_engine as _te_mod
if not hasattr(_te_mod, 'os'):
    _te_mod.os = os

from src.core.thinking_engine import (
    ThinkingEngine,
    GenerationPlan,
    ThinkingResult,
    APP_TEMPLATES,
    AUTOMATION_TEMPLATES,
)


# ============================================================
#  REASON TESTS
# ============================================================

class TestReason:
    """Tests for ThinkingEngine.reason()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_thinking_result(self):
        """Should return a ThinkingResult object."""
        result = self.engine.reason("How to build an API?")
        assert isinstance(result, ThinkingResult)

    def test_no_model_returns_low_confidence(self):
        """Without AI, should return low confidence result."""
        result = self.engine.reason("Test query")
        assert result.confidence <= 0.2
        assert result.source in ("no_model", "semantic_fallback")

    def test_with_context(self):
        """Should accept additional context."""
        result = self.engine.reason("Test", context="Some context")
        assert isinstance(result, ThinkingResult)

    def test_with_mock_ai(self):
        """With mock AI, should return thinking source."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "Use FastAPI with SQLite."
        engine = ThinkingEngine(mini_ai=mock_ai)
        result = engine.reason("How to build an API?")
        assert result.source == "thinking"
        assert result.confidence > 0.5


# ============================================================
#  EVALUATE CODE TESTS
# ============================================================

class TestEvaluateCode:
    """Tests for ThinkingEngine.evaluate_code()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_detects_eval_usage(self):
        """Should detect eval() as security issue."""
        result = self.engine.evaluate_code("x = eval(input())")
        assert any("eval()" in i for i in result["issues"])

    def test_detects_exec_usage(self):
        """Should detect exec() as security issue."""
        result = self.engine.evaluate_code("exec('print(1)')")
        assert any("exec()" in i for i in result["issues"])

    def test_detects_os_system(self):
        """Should detect os.system() as security issue."""
        result = self.engine.evaluate_code("import os\nos.system('ls')")
        assert any("os.system()" in i for i in result["issues"])

    def test_detects_pickle(self):
        """Should detect pickle as security issue."""
        result = self.engine.evaluate_code("import pickle\npickle.loads(data)")
        assert any("pickle" in i for i in result["issues"])

    def test_detects_todo(self):
        """Should detect TODO/FIXME markers."""
        result = self.engine.evaluate_code("def f():\n    # TODO: implement\n    pass")
        assert any("TODO" in i or "FIXME" in i for i in result["issues"])

    def test_suggests_error_handling(self):
        """Should suggest error handling when missing."""
        result = self.engine.evaluate_code("def f(x):\n    return x + 1")
        assert any("error handling" in s.lower() or "try" in s.lower()
                    for s in result["suggestions"])

    def test_returns_quality_score(self):
        """Should return a quality score between 0 and 1."""
        result = self.engine.evaluate_code("x = 1")
        assert 0.0 <= result["quality_score"] <= 1.0

    def test_static_analysis_source(self):
        """Without AI, source should be 'static_analysis'."""
        result = self.engine.evaluate_code("x = 1")
        assert result["source"] == "static_analysis"


# ============================================================
#  DECOMPOSE PROBLEM TESTS
# ============================================================

class TestDecomposeProblem:
    """Tests for ThinkingEngine.decompose_problem()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_list_of_subproblems(self):
        """Should return a list of subproblem dicts."""
        result = self.engine.decompose_problem("Build a web app")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_subproblems_have_required_fields(self):
        """Each subproblem should have name, description, priority."""
        result = self.engine.decompose_problem("Build a web app")
        for sp in result:
            assert "name" in sp
            assert "description" in sp
            assert "priority" in sp

    def test_max_five_subproblems(self):
        """Should return at most 5 subproblems."""
        result = self.engine.decompose_problem("Complex problem")
        assert len(result) <= 5

    def test_auth_keyword_adds_auth_subproblem(self):
        """Auth keyword should add auth subproblem."""
        result = self.engine.decompose_problem("Build an auth system")
        names = [sp["name"] for sp in result]
        assert "implement_auth" in names

    def test_email_keyword_adds_notification_subproblem(self):
        """Email keyword should add notification subproblem."""
        result = self.engine.decompose_problem("System with email notifications")
        names = [sp["name"] for sp in result]
        assert "setup_notifications" in names


# ============================================================
#  DESIGN ARCHITECTURE TESTS
# ============================================================

class TestDesignArchitecture:
    """Tests for ThinkingEngine.design_architecture()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_architecture_dict(self):
        """Should return an architecture dictionary."""
        result = self.engine.design_architecture("Build a CRM")
        assert isinstance(result, dict)
        assert "type" in result
        assert "components" in result

    def test_fallback_monolith_for_app(self):
        """App templates should default to monolith architecture."""
        result = self.engine.design_architecture("Build a CRM")
        assert result["type"] == "monolith"
        assert result["source"] == "fallback"

    def test_fallback_worker_for_automation(self):
        """Automation templates should default to worker architecture."""
        result = self.engine.design_architecture("webhook callback evento")
        assert result["type"] == "worker"

    def test_includes_tech_stack(self):
        """Architecture should include tech stack."""
        result = self.engine.design_architecture("Build a web API")
        assert "tech_stack" in result
        assert len(result["tech_stack"]) > 0

    def test_includes_data_flow(self):
        """Architecture should include data flow description."""
        result = self.engine.design_architecture("Build a CRM")
        assert "data_flow" in result


# ============================================================
#  CHAIN OF THOUGHT TESTS
# ============================================================

class TestChainOfThought:
    """Tests for ThinkingEngine.chain_of_thought()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_no_model_returns_low_confidence(self):
        """Without AI, should return low confidence result."""
        result = self.engine.chain_of_thought("Test problem")
        assert result.confidence <= 0.2
        assert result.source == "no_model"

    def test_with_mock_ai(self):
        """With mock AI, should return chain_of_thought source."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "Step 1: Identify the pattern. Therefore, use caching."
        engine = ThinkingEngine(mini_ai=mock_ai)
        result = engine.chain_of_thought("How to optimize?")
        assert result.source == "chain_of_thought"
        assert result.confidence > 0.3

    def test_max_steps_respected(self):
        """Should limit steps to max_steps."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "Some reasoning step."
        engine = ThinkingEngine(mini_ai=mock_ai)
        result = engine.chain_of_thought("Test", max_steps=2)
        assert result.thinking_time_s >= 0


# ============================================================
#  STATS TESTS
# ============================================================

class TestThinkingStats:
    """Tests for ThinkingEngine.stats property."""

    def test_stats_structure(self):
        """Stats should contain expected keys."""
        engine = ThinkingEngine()
        stats = engine.stats
        assert "total_calls" in stats
        assert "total_thinking_time_s" in stats
        assert "ai_available" in stats
        assert "semantic_available" in stats
        assert "memory_available" in stats
        assert "app_templates" in stats
        assert "automation_templates" in stats

    def test_template_counts(self):
        """Stats should report correct template counts."""
        engine = ThinkingEngine()
        stats = engine.stats
        assert stats["app_templates"] == len(APP_TEMPLATES)
        assert stats["automation_templates"] == len(AUTOMATION_TEMPLATES)

    def test_availability_no_deps(self):
        """Without dependencies, all availability should be False."""
        engine = ThinkingEngine()
        stats = engine.stats
        assert stats["ai_available"] is False
        assert stats["semantic_available"] is False
        assert stats["memory_available"] is False
