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



class TestAutomationNamer:
    """A33: Generate descriptive name for automation."""

    def setup_method(self):
        self.namer = AutomationNamer()

    def test_name_from_description(self):
        """Name should be generated from description keywords."""
        result = self.namer.execute(
            {"description": "send daily email report"}
        )
        assert isinstance(result, NameResult)
        assert result.name != ""
        assert result.slug != ""

    def test_name_from_specs(self):
        """Name should use template when specs provided."""
        result = self.namer.execute({
            "trigger_spec": TriggerSpec(type="schedule"),
            "action_spec": ActionSpec(type="email"),
            "description": "weekly sales report",
        })
        assert "email" in result.name or "schedule" in result.name

    def test_slug_is_url_safe(self):
        """Slug should contain only ASCII, lowercase, hyphens."""
        result = self.namer.execute(
            {"description": "Enviar correo electrónico diario"}
        )
        # Slug should not contain special chars or uppercase
        assert all(c.isalnum() or c == "-" for c in result.slug)
        assert result.slug == result.slug.lower()

    def test_stop_words_removed(self):
        """Stop words should be removed from name."""
        result = self.namer.execute(
            {"description": "the daily report generator"}
        )
        # "the" should be removed
        assert "the" not in result.name.split("_")

    def test_empty_description_fallback(self):
        """Empty description should produce a name."""
        result = self.namer.execute({"description": ""})
        assert result.name != ""

    def test_schedule_email_template(self):
        """schedule + email should use template."""
        result = self.namer.execute({
            "trigger_spec": TriggerSpec(type="schedule"),
            "action_spec": ActionSpec(type="email"),
            "description": "customer digest",
        })
        assert "email" in result.name

    def test_fallback_returns_generic(self):
        """Fallback should return generic name."""
        result = self.namer.fallback(None)
        assert "automation" in result.name
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A34 WorkflowSerializer Tests
# ═══════════════════════════════════════════════════════════

