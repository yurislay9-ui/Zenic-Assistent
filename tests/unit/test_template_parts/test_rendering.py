"""Tests for app and automation rendering."""

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


class TestAppRendering:
    """Test full app rendering via TemplateEngine."""

    def _make_simple_plan(self, **overrides):
        defaults = {
            "base_template": "apps/base",
            "app_template": "",
            "blocks": [],
            "variables": {
                "project_name": "test_app",
                "app_name": "test_app",
                "template_type": "generic",
                "db_name": "test.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            "entities": [
                {"name": "Item", "fields": ["name:str", "description:str", "price:float"]},
            ],
        }
        defaults.update(overrides)
        return CompositionPlan(**defaults)

    def test_render_simple_app(self):
        """Render a simple app with one entity."""
        engine = TemplateEngine()
        plan = self._make_simple_plan()
        files = engine.render_app(plan)
        assert "main.py" in files
        assert "database.py" in files
        assert "models.py" in files
        assert "services.py" in files
        assert "config.py" in files
        assert "validators.py" in files
        assert len(files) > 5

    def test_render_app_with_blocks(self):
        """Render an app with business logic blocks."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="",
            blocks=["invoice_calculator", "email_smtp"],
            variables={
                "project_name": "billing_app",
                "app_name": "billing_app",
                "template_type": "invoice_billing",
                "db_name": "billing.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[
                {"name": "Customer", "fields": ["name:str", "email:str"]},
                {"name": "Invoice", "fields": ["customer_id:int", "total:float", "status:str"]},
            ],
        )
        files = engine.render_app(plan)
        assert "main.py" in files
        assert "blocks/invoice_calculator.py" in files
        assert "blocks/email_smtp.py" in files

    def test_rendered_code_has_no_stubs(self):
        """Rendered code should not contain logger.info stubs or placeholder returns."""
        engine = TemplateEngine()
        plan = self._make_simple_plan(
            entities=[{"name": "Item", "fields": ["name:str", "price:float"]}],
        )
        files = engine.render_app(plan)
        services = files.get("services.py", "")
        assert '{"processed": True' not in services
        assert 'logger.info("Sending' not in services

    def test_rendered_sql_is_parameterized(self):
        """All SQL in rendered code uses ? parameterized queries."""
        engine = TemplateEngine()
        plan = self._make_simple_plan(
            entities=[{"name": "Item", "fields": ["name:str", "price:float"]}],
        )
        files = engine.render_app(plan)
        services = files.get("services.py", "")
        database = files.get("database.py", "")
        assert "?" in services or "?" in database

    def test_rendered_code_imports_fastapi(self):
        """Rendered main.py imports FastAPI."""
        engine = TemplateEngine()
        plan = self._make_simple_plan(
            entities=[{"name": "Item", "fields": ["name:str"]}],
        )
        files = engine.render_app(plan)
        main = files.get("main.py", "")
        assert "fastapi" in main.lower() or "FastAPI" in main


class TestAutomationRendering:
    """Test automation project rendering."""

    def test_render_automation(self):
        """Render a basic automation project."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="automations/base",
            app_template="",
            blocks=["email_smtp"],
            variables={
                "project_name": "daily_report",
                "app_name": "daily_report",
                "template_type": "automation",
                "db_name": "automation.db",
                "port": 8001,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[{
                "name": "daily_report",
                "fields": [],
                "trigger_config": {"type": "cron", "hour": 9, "minute": 0},
                "actions": [{"type": "send_email", "config": {"to": "admin@co.com", "subject": "Report"}}],
            }],
        )
        files = engine.render_automation(plan)
        assert "main.py" in files
        assert "actions.py" in files
        assert "config.py" in files

    def test_automation_actions_are_real(self):
        """Rendered actions.py contains real implementations, not stubs."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="automations/base",
            app_template="",
            blocks=["email_smtp"],
            variables={
                "project_name": "test_auto",
                "app_name": "test_auto",
                "template_type": "automation",
                "db_name": "auto.db",
                "port": 8001,
                "secret_key": "test",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[{
                "name": "test",
                "fields": [],
                "trigger_config": {"type": "cron", "hour": 9},
                "actions": [{"type": "send_email", "config": {"to": "a@b.com"}}],
            }],
        )
        files = engine.render_automation(plan)
        actions = files.get("actions.py", "")
        assert "smtplib" in actions or "aiosmtplib" in actions
        assert 'logger.info("Automation: Email to' not in actions
