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



class TestWorkflowSerializer:
    """A34: Serialize automation into executable workflow spec."""

    def setup_method(self):
        self.serializer = WorkflowSerializer()

    def test_basic_serialization(self):
        """Basic serialization should produce valid WorkflowSpec."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="schedule", config={"interval": "daily"}),
            "actions": [ActionSpec(type="email", config={"to": "admin@test.com"})],
            "schedule": ScheduleSpec(type="cron", cron="0 9 * * *"),
            "name": "daily_report",
            "description": "Send daily report email",
        })
        assert isinstance(result, WorkflowSpec)
        assert result.yaml != ""
        assert result.json_spec != ""
        assert isinstance(result.executable, dict)

    def test_executable_has_required_fields(self):
        """Executable dict should have all required fields."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="manual"),
            "actions": [ActionSpec(type="log")],
            "name": "test_workflow",
        })
        exe = result.executable
        assert "version" in exe
        assert "name" in exe
        assert "trigger" in exe
        assert "actions" in exe
        assert "schedule" in exe

    def test_json_is_valid(self):
        """JSON output should be valid JSON."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="schedule"),
            "actions": [ActionSpec(type="notification")],
            "name": "json_test",
        })
        parsed = json.loads(result.json_spec)
        assert isinstance(parsed, dict)
        assert parsed["name"] == "json_test"

    def test_yaml_not_empty(self):
        """YAML output should not be empty."""
        result = self.serializer.execute({
            "trigger": {"type": "webhook"},
            "actions": [{"type": "http"}],
            "name": "yaml_test",
        })
        assert len(result.yaml) > 0
        assert "yaml_test" in result.yaml

    def test_conditions_included(self):
        """Conditions should be included in executable."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="event"),
            "actions": [ActionSpec(type="notification")],
            "conditions": ["status == 'critical'"],
            "name": "conditional_test",
        })
        assert "conditions" in result.executable
        assert len(result.executable["conditions"]) > 0

    def test_condition_result_object(self):
        """ConditionResult object should be handled."""
        cond_result = ConditionResult(
            conditions=["balance > 1000"],
            logic_tree={"operator": "SINGLE"},
        )
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="schedule"),
            "actions": [ActionSpec(type="email")],
            "conditions": cond_result,
            "name": "cond_result_test",
        })
        assert "conditions" in result.executable

    def test_metadata_included(self):
        """Metadata should be included in executable."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="manual"),
            "actions": [ActionSpec(type="log")],
            "name": "meta_test",
        })
        assert "metadata" in result.executable
        assert result.executable["metadata"]["deterministic"] is True

    def test_empty_actions_gets_default(self):
        """Empty actions should get a default log action."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="manual"),
            "name": "empty_actions",
        })
        assert len(result.executable["actions"]) > 0

    def test_fallback_returns_minimal(self):
        """Fallback should return minimal workflow."""
        result = self.serializer.fallback(None)
        assert isinstance(result, WorkflowSpec)
        assert result.source == "fallback"
        assert result.executable.get("name") == "empty_workflow"


# ═══════════════════════════════════════════════════════════
# Integration: Full Automation Pipeline Test
# ═══════════════════════════════════════════════════════════

