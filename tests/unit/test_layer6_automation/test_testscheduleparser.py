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

from src.core.agents_v2.automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    ConditionExtractor,
    AutomationNamer,
    WorkflowSerializer,
)
from src.core.agents_v2.schemas import (
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



class TestScheduleParser:
    """A31: Parse natural language schedule into cron/interval."""

    def setup_method(self):
        self.parser = ScheduleParser()

    def test_daily_schedule(self):
        """'daily' should produce daily cron."""
        result = self.parser.execute({"description": "run daily"})
        assert isinstance(result, ScheduleSpec)
        assert result.type == "cron"
        assert "0" in result.cron  # minute 0
        assert result.cron.count("*") >= 2  # daily pattern

    def test_hourly_schedule(self):
        """'hourly' should produce interval schedule."""
        result = self.parser.execute({"description": "run hourly"})
        assert result.type == "interval"
        assert result.interval_seconds == 3600

    def test_weekly_schedule(self):
        """'weekly' should produce weekly cron."""
        result = self.parser.execute({"description": "run weekly"})
        assert result.type == "cron"
        assert result.interval_seconds == 604800

    def test_monthly_schedule(self):
        """'monthly' should produce monthly cron."""
        result = self.parser.execute({"description": "run monthly"})
        assert result.type == "cron"

    def test_specific_hour(self):
        """'at 3pm' should set hour 15 in cron."""
        result = self.parser.execute({"description": "run daily at 3pm"})
        assert result.type == "cron"
        assert "15" in result.cron

    def test_interval_pattern_es(self):
        """'cada 30 minutos' should produce interval."""
        result = self.parser.execute({"description": "cada 30 minutos"})
        assert result.type == "interval"
        assert result.interval_seconds == 30 * 60

    def test_interval_pattern_en(self):
        """'every 2 hours' should produce interval."""
        result = self.parser.execute({"description": "every 2 hours"})
        assert result.type == "interval"
        assert result.interval_seconds == 2 * 3600

    def test_cron_expression_direct(self):
        """Direct cron expression should be parsed."""
        result = self.parser.execute({"description": "0 9 * * 1-5"})
        assert result.type == "cron"
        assert "0 9 * * 1-5" in result.cron

    def test_day_of_week_es(self):
        """'viernes' should set day of week in cron."""
        result = self.parser.execute({"description": "semanal viernes"})
        assert result.type == "cron"
        assert "5" in result.cron  # Friday = 5

    def test_manual_default(self):
        """No schedule pattern should default to manual."""
        result = self.parser.execute({"description": "process data"})
        assert result.type == "manual"

    def test_empty_description_manual(self):
        """Empty description should default to manual."""
        result = self.parser.execute({"description": ""})
        assert result.type == "manual"

    def test_string_input_works(self):
        """String input should work."""
        result = self.parser.execute("run daily")
        assert result.type == "cron"

    def test_fallback_returns_manual(self):
        """Fallback should return manual."""
        result = self.parser.fallback(None)
        assert result.type == "manual"
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A32 ConditionExtractor Tests
# ═══════════════════════════════════════════════════════════

