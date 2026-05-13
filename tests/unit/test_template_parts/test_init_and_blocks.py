"""Tests for TemplateEngine init, blocks, and suggestions."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.template_engine import (
    TemplateEngine,
    TemplateBlock,
    CompositionPlan,
    TEMPLATE_ROOT,
)


class TestTemplateEngineInit:
    """Test TemplateEngine initialization."""

    def test_init_with_default_root(self):
        """Engine initializes with default template root."""
        engine = TemplateEngine()
        assert engine._root == TEMPLATE_ROOT
        assert engine.stats["jinja2_available"] is True

    def test_init_with_custom_root(self, tmp_path):
        """Engine initializes with custom template root."""
        engine = TemplateEngine(template_root=str(tmp_path))
        assert engine._root == str(tmp_path)

    def test_builtin_blocks_registered(self):
        """All 21 builtin blocks are registered."""
        engine = TemplateEngine()
        assert len(engine._blocks) >= 21

    def test_block_categories(self):
        """All expected categories are present."""
        engine = TemplateEngine()
        categories = engine.stats["block_categories"]
        assert "business_logic" in categories
        assert "integrations" in categories
        assert "auth" in categories
        assert "data" in categories


class TestTemplateBlock:
    """Test TemplateBlock data structure."""

    def test_block_creation(self):
        """Block can be created with all fields."""
        block = TemplateBlock(
            name="test_block",
            category="business_logic",
            description="Test block",
            inputs=["data"],
            outputs=["result"],
            dependencies=["other_block"],
        )
        assert block.name == "test_block"
        assert block.category == "business_logic"
        assert block.dependencies == ["other_block"]

    def test_register_custom_block(self):
        """Custom blocks can be registered."""
        engine = TemplateEngine()
        block = TemplateBlock(
            name="custom_test",
            category="business_logic",
            description="Custom test block",
        )
        engine.register_block(block)
        assert engine.get_block("custom_test") is not None
        assert engine.get_block("custom_test").name == "custom_test"


class TestBlockSuggestion:
    """Test block suggestion based on description."""

    def test_suggest_email_blocks(self):
        """Email-related description suggests email blocks."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("enviar email con factura al cliente")
        assert "email_smtp" in blocks

    def test_suggest_auth_blocks(self):
        """Auth-related description suggests auth blocks."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("sistema con login y usuarios")
        assert "jwt_auth" in blocks

    def test_suggest_invoice_blocks(self):
        """Invoice description suggests invoice calculator."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("facturacion con calculo de impuestos")
        assert "invoice_calculator" in blocks

    def test_suggest_inventory_blocks(self):
        """Inventory description suggests inventory tracker."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("control de inventario y stock")
        assert "inventory_tracker" in blocks

    def test_suggest_crud_blocks(self):
        """CRUD description suggests CRUD service."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("crud de base de datos")
        assert "crud_service" in blocks

    def test_dependency_resolution(self):
        """Dependencies are resolved in correct order."""
        engine = TemplateEngine()
        resolved = engine.resolve_dependencies(["notification_manager"])
        nm_idx = resolved.index("notification_manager")
        if "email_smtp" in resolved:
            assert resolved.index("email_smtp") < nm_idx
        if "telegram_bot" in resolved:
            assert resolved.index("telegram_bot") < nm_idx

    def test_rbac_depends_on_jwt(self):
        """RBAC block depends on JWT auth."""
        engine = TemplateEngine()
        resolved = engine.resolve_dependencies(["rbac"])
        if "jwt_auth" in resolved and "rbac" in resolved:
            assert resolved.index("jwt_auth") < resolved.index("rbac")
