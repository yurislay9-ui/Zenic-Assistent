"""
Tests for Code and Automation schemas.
"""

import pytest
from dataclasses import fields

from src.core.agents.schemas import (
    CodeInput, FileSpec, CodeOutput,
    AutomationInput, TriggerSpec, ActionSpec, ScheduleSpec, AutomationOutput,
)


# ============================================================
#  CODE SCHEMAS
# ============================================================

class TestCodeInput:
    """Tests for CodeInput schema."""

    def test_default_values(self):
        """Should have generate/python as defaults."""
        inp = CodeInput()
        assert inp.task == "generate"
        assert inp.language == "python"
        assert inp.requirements == ""
        assert inp.existing_code == ""
        assert inp.constraints == {}

    def test_custom_task(self):
        """Should accept valid task types."""
        for task in ["generate", "transform", "scaffold", "optimize", "fix"]:
            inp = CodeInput(task=task)
            assert inp.task == task


class TestFileSpec:
    """Tests for FileSpec schema."""

    def test_default_values(self):
        """Should have empty string defaults."""
        spec = FileSpec()
        assert spec.path == ""
        assert spec.content == ""
        assert spec.language == ""

    def test_custom_values(self):
        """Should accept file specification data."""
        spec = FileSpec(path="main.py", content="print('hi')", language="python")
        assert spec.path == "main.py"
        assert spec.content == "print('hi')"


class TestCodeOutput:
    """Tests for CodeOutput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        out = CodeOutput()
        assert out.code == ""
        assert out.language == "python"
        assert out.files == []
        assert out.test_code == ""
        assert out.explanation == ""

    def test_with_files(self):
        """Should accept a list of FileSpec."""
        files = [FileSpec(path="a.py", content="code", language="python")]
        out = CodeOutput(code="main()", files=files)
        assert len(out.files) == 1
        assert out.files[0].path == "a.py"


# ============================================================
#  AUTOMATION SCHEMAS
# ============================================================

class TestAutomationInput:
    """Tests for AutomationInput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        inp = AutomationInput()
        assert inp.description == ""
        assert inp.context == {}


class TestTriggerSpec:
    """Tests for TriggerSpec schema."""

    def test_default_type_is_manual(self):
        """Should default to manual trigger."""
        t = TriggerSpec()
        assert t.type == "manual"
        assert t.config == {}

    def test_valid_trigger_types(self):
        """Should accept valid trigger types."""
        for tt in ["manual", "schedule", "event", "webhook"]:
            t = TriggerSpec(type=tt)
            assert t.type == tt


class TestActionSpec:
    """Tests for ActionSpec schema."""

    def test_default_type_is_log(self):
        """Should default to log action."""
        a = ActionSpec()
        assert a.type == "log"


class TestScheduleSpec:
    """Tests for ScheduleSpec schema."""

    def test_default_values(self):
        """Should have manual/zero defaults."""
        s = ScheduleSpec()
        assert s.type == "manual"
        assert s.interval_seconds == 0
        assert s.cron_expression == ""


class TestAutomationOutput:
    """Tests for AutomationOutput schema."""

    def test_default_values(self):
        """Should have unnamed automation defaults."""
        out = AutomationOutput()
        assert out.name == "unnamed_automation"
        assert out.triggers == []
        assert out.actions == []
        assert isinstance(out.schedule, ScheduleSpec)
        assert out.conditions == []

    def test_with_triggers_and_actions(self):
        """Should accept lists of TriggerSpec and ActionSpec."""
        out = AutomationOutput(
            name="daily_report",
            triggers=[TriggerSpec(type="schedule")],
            actions=[ActionSpec(type="email")],
        )
        assert out.name == "daily_report"
        assert len(out.triggers) == 1
        assert len(out.actions) == 1
