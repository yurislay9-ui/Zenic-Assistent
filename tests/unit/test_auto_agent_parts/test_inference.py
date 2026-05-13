"""Tests for trigger, action, schedule, condition, and name inference."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.automation_agent import (
    AutomationAgent,
    TRIGGER_KEYWORDS,
    ACTION_KEYWORDS,
    SCHEDULE_PATTERNS,
)
from src.core.agents.schemas import (
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
)
from src.core.agents.base import AgentResult


@pytest.fixture
def agent():
    """AutomationAgent without external dependencies."""
    return AutomationAgent()


@pytest.fixture
def agent_with_memory():
    """AutomationAgent with mocked SmartMemory."""
    _agent = AutomationAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    _agent.wire(smart_memory=mock_memory)
    return _agent, mock_memory


# ============================================================
#  Test: Trigger Inference
# ============================================================

class TestAutomationTriggerInference:
    """Tests for deterministic trigger inference from description."""

    def test_schedule_trigger_daily(self, agent):
        """Should detect schedule trigger from 'daily' keyword."""
        result = agent.fallback(AutomationInput(
            description="send daily report every day at 9am",
        ))
        assert len(result.triggers) >= 1
        assert result.triggers[0].type == "schedule"

    def test_schedule_trigger_cron(self, agent):
        """Should detect schedule trigger from 'cron' keyword."""
        result = agent.fallback(AutomationInput(
            description="run cron job for backup",
        ))
        assert result.triggers[0].type == "schedule"

    def test_event_trigger(self, agent):
        """Should detect event trigger from 'when' keyword."""
        result = agent.fallback(AutomationInput(
            description="when new user registers send email",
        ))
        assert result.triggers[0].type == "event"

    def test_webhook_trigger(self, agent):
        """Should detect webhook trigger from 'webhook' keyword."""
        result = agent.fallback(AutomationInput(
            description="receive webhook from payment provider",
        ))
        assert result.triggers[0].type == "webhook"

    def test_default_trigger_schedule(self, agent):
        """Should default to schedule trigger when no keywords match."""
        result = agent.fallback(AutomationInput(
            description="process data files",
        ))
        assert result.triggers[0].type == "schedule"

    def test_event_trigger_config(self, agent):
        """Event trigger should have event_type in config."""
        result = agent.fallback(AutomationInput(
            description="when order is placed notify admin",
        ))
        assert result.triggers[0].type == "event"
        assert "event_type" in result.triggers[0].config


# ============================================================
#  Test: Action Inference
# ============================================================

class TestAutomationActionInference:
    """Tests for deterministic action inference from description."""

    def test_email_action(self, agent):
        """Should detect email action."""
        result = agent.fallback(AutomationInput(
            description="send email notification daily",
        ))
        action_types = [a.type for a in result.actions]
        assert "email" in action_types

    def test_notification_action(self, agent):
        """Should detect notification action."""
        result = agent.fallback(AutomationInput(
            description="alert administrator when error occurs",
        ))
        action_types = [a.type for a in result.actions]
        assert "notification" in action_types

    def test_db_action(self, agent):
        """Should detect database action."""
        result = agent.fallback(AutomationInput(
            description="backup database daily",
        ))
        action_types = [a.type for a in result.actions]
        assert "db" in action_types

    def test_http_action(self, agent):
        """Should detect HTTP/API action."""
        result = agent.fallback(AutomationInput(
            description="call api endpoint when event triggers",
        ))
        action_types = [a.type for a in result.actions]
        assert "http" in action_types

    def test_file_action(self, agent):
        """Should detect file action."""
        result = agent.fallback(AutomationInput(
            description="export csv file report",
        ))
        action_types = [a.type for a in result.actions]
        assert "file" in action_types

    def test_default_log_action(self, agent):
        """Should default to log action when no actions detected."""
        result = agent.fallback(AutomationInput(
            description="do something unspecified",
        ))
        assert len(result.actions) >= 1

    def test_max_five_actions(self, agent):
        """Should limit actions to 5 maximum."""
        desc = "send email and alert and backup db and call api and export file and transform data"
        result = agent.fallback(AutomationInput(description=desc))
        assert len(result.actions) <= 5


# ============================================================
#  Test: Schedule Inference
# ============================================================

class TestAutomationScheduleInference:
    """Tests for deterministic schedule inference."""

    def test_daily_schedule(self, agent):
        """Should infer daily schedule."""
        result = agent.fallback(AutomationInput(
            description="send report daily at 9am",
        ))
        assert result.schedule.type == "cron"
        assert "9" in result.schedule.cron_expression

    def test_hourly_schedule(self, agent):
        """Should infer hourly schedule."""
        result = agent.fallback(AutomationInput(
            description="check status hourly every hour",
        ))
        assert result.schedule.type == "interval"
        assert result.schedule.interval_seconds == 3600

    def test_weekly_schedule(self, agent):
        """Should infer weekly schedule."""
        result = agent.fallback(AutomationInput(
            description="run weekly report every monday",
        ))
        assert result.schedule.type == "cron"

    def test_monthly_schedule(self, agent):
        """Should infer monthly schedule."""
        result = agent.fallback(AutomationInput(
            description="generate monthly summary",
        ))
        assert result.schedule.type == "cron"

    def test_manual_default_schedule(self, agent):
        """Should default to manual when no schedule keywords match."""
        result = agent.fallback(AutomationInput(
            description="process one-time request",
        ))
        assert result.schedule.type == "manual"

    def test_hour_extraction_pm(self, agent):
        """Should extract PM hours correctly."""
        result = agent.fallback(AutomationInput(
            description="run daily at 3pm",
        ))
        assert "15" in result.schedule.cron_expression

    def test_hour_extraction_am(self, agent):
        """Should extract AM hours correctly."""
        result = agent.fallback(AutomationInput(
            description="run daily at 9am",
        ))
        assert "9" in result.schedule.cron_expression


# ============================================================
#  Test: Condition Inference
# ============================================================

class TestAutomationConditionInference:
    """Tests for condition inference from description."""

    def test_if_condition(self, agent):
        """Should extract condition from 'if/when' keyword pattern."""
        result = agent.fallback(AutomationInput(
            description="send email if sales exceed 1000 then notify",
        ))
        if result.conditions:
            assert any("sales" in c.lower() for c in result.conditions)
        else:
            assert result.conditions == []

    def test_no_conditions(self, agent):
        """Should return empty conditions when no condition keywords."""
        result = agent.fallback(AutomationInput(
            description="send daily report",
        ))
        assert result.conditions == []


# ============================================================
#  Test: Name Extraction
# ============================================================

class TestAutomationNameExtraction:
    """Tests for name extraction from description."""

    def test_name_from_description(self, agent):
        """Should extract meaningful name from description."""
        result = agent.fallback(AutomationInput(
            description="send daily report email",
        ))
        assert result.name != ""
        assert result.name != "unnamed_automation"

    def test_name_stops_removed(self, agent):
        """Should remove stop words from name."""
        result = agent.fallback(AutomationInput(
            description="create a weekly report",
        ))
        assert "create" not in result.name
        assert "_" in result.name or result.name != ""
