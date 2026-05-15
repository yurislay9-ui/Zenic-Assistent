"""
Tests for Layer 6: Automation agents (A29-A34).

All 6 agents tested:
  - A29 TriggerInferrer
  - A30 ActionInferrer
  - A31 ScheduleParser
  - A32 ConditionExtractor
  - A33 AutomationNamer
  - A34 WorkflowSerializer
"""

import json
import pytest

from src.core.agents.automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    ConditionExtractor,
    AutomationNamer,
    WorkflowSerializer,
)
from src.core.agents.schemas import (
    AutoDescription,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
    ConditionResult,
    NameResult,
    WorkflowSpec,
)


# ═══════════════════════════════════════════════════════════
# A29 TriggerInferrer Tests
# ═══════════════════════════════════════════════════════════



class TestActionInferrer:
    """A30: Infer action types from description."""

    def setup_method(self):
        self.inferrer = ActionInferrer()

    def test_email_action(self):
        """'email' should detect email action."""
        result = self.inferrer.execute({"description": "send an email notification"})
        assert isinstance(result, ActionSpec)
        assert result.type == "email"

    def test_notification_action(self):
        """'alertar' should detect notification action."""
        result = self.inferrer.execute({"description": "alertar al administrador"})
        assert result.type == "notification"

    def test_db_action(self):
        """'backup' should detect db action."""
        result = self.inferrer.execute({"description": "make a database backup"})
        assert result.type == "db"

    def test_http_action(self):
        """'api' should detect http action."""
        result = self.inferrer.execute({"description": "call an API endpoint"})
        assert result.type == "http"

    def test_file_action(self):
        """'csv' should detect file action."""
        result = self.inferrer.execute({"description": "export data to csv"})
        assert result.type == "file"

    def test_transform_action(self):
        """'convertir' should detect transform action."""
        result = self.inferrer.execute({"description": "convertir datos a formato JSON"})
        assert result.type == "transform"

    def test_log_action(self):
        """'log' should detect log action."""
        result = self.inferrer.execute({"description": "registrar la operación"})
        assert result.type == "log"

    def test_default_log_when_no_match(self):
        """No matching keywords should default to log action."""
        result = self.inferrer.execute({"description": "do something"})
        assert result.type == "log"

    def test_multiple_actions_via_infer_all(self):
        """Multiple action types should be detected via infer_all()."""
        actions = self.inferrer.infer_all(
            {"description": "send email and export to csv"}
        )
        types = {a.type for a in actions}
        assert "email" in types
        assert "file" in types

    def test_infer_all_max_5(self):
        """infer_all should cap at 5 actions."""
        actions = self.inferrer.infer_all(
            {"description": "send email, alert, backup db, call api, export csv, transform, log"}
        )
        assert len(actions) <= 5

    def test_email_address_extraction(self):
        """Email address in description should be extracted to config."""
        result = self.inferrer.execute(
            {"description": "send email to admin@company.com"}
        )
        assert result.type == "email"
        assert result.config.get("to") == "admin@company.com"

    def test_empty_description_default_log(self):
        """Empty description should default to log action."""
        result = self.inferrer.execute({"description": ""})
        assert result.type == "log"

    def test_fallback_returns_log(self):
        """Fallback should return log action."""
        result = self.inferrer.fallback(None)
        assert result.type == "log"
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A31 ScheduleParser Tests
# ═══════════════════════════════════════════════════════════

