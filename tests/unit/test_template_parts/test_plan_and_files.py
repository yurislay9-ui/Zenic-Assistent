"""Tests for CompositionPlan, block files, and block listing."""

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


class TestCompositionPlan:
    """Test CompositionPlan data structure."""

    def test_default_values(self):
        """CompositionPlan has sensible defaults."""
        plan = CompositionPlan()
        assert plan.base_template == "apps/base"
        assert plan.blocks == []
        assert plan.entities == []
        assert plan.variables == {}

    def test_full_plan(self):
        """CompositionPlan can be fully specified."""
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="invoice_billing",
            blocks=["invoice_calculator", "email_smtp", "jwt_auth"],
            variables={"project_name": "billing"},
            entities=[{"name": "Invoice", "fields": ["total:float"]}],
        )
        assert plan.app_template == "invoice_billing"
        assert len(plan.blocks) == 3


class TestBlockFiles:
    """Test that block template files exist and are valid."""

    def test_business_logic_blocks_exist(self):
        """All business logic block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("business_logic"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"

    def test_integration_blocks_exist(self):
        """All integration block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("integrations"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"

    def test_auth_blocks_exist(self):
        """All auth block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("auth"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"

    def test_data_blocks_exist(self):
        """All data block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("data"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"


class TestListBlocks:
    """Test block listing and filtering."""

    def test_list_all_blocks(self):
        """Can list all registered blocks."""
        engine = TemplateEngine()
        all_blocks = engine.list_blocks()
        assert len(all_blocks) >= 21

    def test_filter_by_category(self):
        """Can filter blocks by category."""
        engine = TemplateEngine()
        biz = engine.list_blocks("business_logic")
        assert all(b.category == "business_logic" for b in biz)
        assert len(biz) >= 7

    def test_integration_count(self):
        """Correct number of integration blocks."""
        engine = TemplateEngine()
        integrations = engine.list_blocks("integrations")
        assert len(integrations) >= 6

    def test_auth_count(self):
        """Correct number of auth blocks."""
        engine = TemplateEngine()
        auth = engine.list_blocks("auth")
        assert len(auth) >= 3

    def test_data_count(self):
        """Correct number of data blocks."""
        engine = TemplateEngine()
        data = engine.list_blocks("data")
        assert len(data) >= 4
