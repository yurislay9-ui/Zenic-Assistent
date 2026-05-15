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



class TestTriggerInferrer:
    """A29: Infer trigger type from description."""

    def setup_method(self):
        self.inferrer = TriggerInferrer()

    def test_schedule_trigger_daily(self):
        """'daily' should detect schedule trigger."""
        result = self.inferrer.execute({"description": "run this daily at 9am"})
        assert isinstance(result, TriggerSpec)
        assert result.type == "schedule"
        assert result.config.get("interval") == "daily"

    def test_schedule_trigger_semanal(self):
        """'semanal' (ES) should detect schedule trigger."""
        result = self.inferrer.execute({"description": "ejecutar semanal"})
        assert result.type == "schedule"
        assert result.config.get("interval") == "weekly"

    def test_event_trigger(self):
        """'when' should detect event trigger."""
        result = self.inferrer.execute({"description": "when a new user registers"})
        assert result.type == "event"

    def test_event_trigger_es(self):
        """'cuando' should detect event trigger."""
        result = self.inferrer.execute({"description": "cuando se detecte un error"})
        assert result.type == "event"

    def test_webhook_trigger(self):
        """'webhook' should detect webhook trigger."""
        result = self.inferrer.execute({"description": "receive a webhook from Stripe"})
        assert result.type == "webhook"
        assert "path" in result.config

    def test_manual_default(self):
        """No matching keywords should default to manual."""
        result = self.inferrer.execute({"description": "process data"})
        assert result.type == "manual"

    def test_empty_description_manual(self):
        """Empty description should default to manual."""
        result = self.inferrer.execute({"description": ""})
        assert result.type == "manual"

    def test_string_input_works(self):
        """String input should work."""
        result = self.inferrer.execute("run hourly")
        assert result.type == "schedule"

    def test_auto_description_input(self):
        """AutoDescription object should work."""
        desc = AutoDescription(description="send email weekly")
        result = self.inferrer.execute(desc)
        assert result.type == "schedule"

    def test_hour_extraction(self):
        """'at 3pm' should extract hour 15."""
        result = self.inferrer.execute({"description": "run daily at 3pm"})
        assert result.type == "schedule"
        assert result.config.get("hour") == 15

    def test_webhook_priority_over_schedule(self):
        """'webhook' should take priority over schedule keywords."""
        result = self.inferrer.execute({"description": "receive a webhook every hour"})
        assert result.type == "webhook"

    def test_fallback_returns_manual(self):
        """Fallback should return manual trigger."""
        result = self.inferrer.fallback(None)
        assert result.type == "manual"
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A30 ActionInferrer Tests
# ═══════════════════════════════════════════════════════════

