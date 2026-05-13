"""Tests for ThinkingEngine init, plan generation, select/customize templates."""

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
#  INITIALIZATION TESTS
# ============================================================

class TestThinkingEngineInit:
    """Tests for ThinkingEngine initialization."""

    def test_init_no_dependencies(self):
        """Should initialize without any AI dependencies."""
        engine = ThinkingEngine()
        assert engine._ai is None
        assert engine._semantic is None
        assert engine._memory is None
        assert engine._call_count == 0
        assert engine._thinking_time == 0.0

    def test_init_with_mock_ai(self):
        """Should accept optional AI engine."""
        mock_ai = MagicMock()
        engine = ThinkingEngine(mini_ai=mock_ai)
        assert engine._ai is mock_ai

    def test_init_with_all_layers(self):
        """Should accept all three AI layers."""
        mock_ai = MagicMock()
        mock_semantic = MagicMock()
        mock_memory = MagicMock()
        engine = ThinkingEngine(
            mini_ai=mock_ai,
            semantic_engine=mock_semantic,
            smart_memory=mock_memory,
        )
        assert engine._ai is mock_ai
        assert engine._semantic is mock_semantic
        assert engine._memory is mock_memory


# ============================================================
#  PLAN GENERATION TESTS
# ============================================================

class TestPlanGeneration:
    """Tests for ThinkingEngine.plan_generation()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_generation_plan(self):
        """Should return a GenerationPlan object."""
        plan = self.engine.plan_generation("Build a CRM system")
        assert isinstance(plan, GenerationPlan)

    def test_identifies_crm_template(self):
        """Should identify 'crm' template from CRM description."""
        plan = self.engine.plan_generation("Necesito un sistema CRM para clientes y ventas")
        assert plan.template_type == "crm"

    def test_identifies_inventory_template(self):
        """Should identify 'inventory' template from inventory description."""
        plan = self.engine.plan_generation("Sistema de inventario y stock")
        assert plan.template_type == "inventory"

    def test_identifies_auth_template(self):
        """Should identify 'auth_system' template from auth description."""
        plan = self.engine.plan_generation("Auth and login system")
        assert plan.template_type == "auth_system"

    def test_identifies_webhook_template(self):
        """Should identify 'webhook_handler' template."""
        plan = self.engine.plan_generation("webhook handler for events")
        assert plan.template_type == "webhook_handler"

    def test_generic_for_unknown(self):
        """Should return 'generic' for unrecognized descriptions."""
        plan = self.engine.plan_generation("something completely unknown xyz")
        assert plan.template_type == "generic"

    def test_includes_entities(self):
        """Plan should include entity definitions."""
        plan = self.engine.plan_generation("CRM system for customers")
        assert len(plan.entities) > 0

    def test_includes_modules(self):
        """Plan should include module definitions."""
        plan = self.engine.plan_generation("CRM system")
        assert len(plan.modules) > 0

    def test_includes_endpoints(self):
        """Plan should include endpoint definitions."""
        plan = self.engine.plan_generation("CRM system")
        assert len(plan.endpoints) > 0

    def test_includes_config(self):
        """Plan should include config variables."""
        plan = self.engine.plan_generation("CRM system")
        assert isinstance(plan.config_vars, dict)
        assert "db_name" in plan.config_vars

    def test_fallback_source_no_ai(self):
        """Without AI, plan source should be 'fallback'."""
        plan = self.engine.plan_generation("Test")
        assert plan.source == "fallback"


# ============================================================
#  SELECT TEMPLATE TESTS
# ============================================================

class TestSelectTemplate:
    """Tests for ThinkingEngine.select_template()."""

    def setup_method(self):
        self.engine = ThinkingEngine()

    def test_returns_template_and_confidence(self):
        """Should return (template_name, confidence) tuple."""
        template, confidence = self.engine.select_template("Build a CRM")
        assert isinstance(template, str)
        assert isinstance(confidence, float)

    def test_crm_selection(self):
        """Should select CRM template for CRM-related request."""
        template, _ = self.engine.select_template("Necesito un sistema CRM")
        assert template == "crm"

    def test_confidence_range(self):
        """Confidence should be between 0.0 and 1.0."""
        _, confidence = self.engine.select_template("Any request")
        assert 0.0 <= confidence <= 1.0


# ============================================================
#  CUSTOMIZE TEMPLATE TESTS
# ============================================================

class TestCustomizeTemplate:
    """Tests for ThinkingEngine.customize_template()."""

    def setup_method(self):
        self.engine = ThinkingEngine()

    def test_simple_substitution(self):
        """Should substitute __PLACEHOLDER__ variables."""
        template = "Hello __NAME__, welcome to __APP__!"
        result = self.engine.customize_template(template, {"NAME": "World", "APP": "ZENIC"})
        assert "Hello World" in result
        assert "welcome to ZENIC" in result

    def test_unfilled_gaps_get_defaults(self):
        """Unfilled gaps should get default values."""
        template = "Port: __PORT__"
        result = self.engine.customize_template(template, {"port": 8080})
        assert "8080" in result

    def test_no_gaps_unchanged(self):
        """Template without gaps should be unchanged (except potential enhancement)."""
        template = "Simple text without gaps"
        result = self.engine.customize_template(template, {})
        assert "Simple text without gaps" in result
