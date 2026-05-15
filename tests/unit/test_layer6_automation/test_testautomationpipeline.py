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



class TestAutomationPipeline:
    """End-to-end automation pipeline through all Layer 6 agents."""

    def test_full_automation_pipeline_es(self):
        """Full pipeline in Spanish: 'Enviar correo diario si el inventario es bajo'"""
        desc = "Enviar correo electrónico diario si el inventario es bajo"

        # Step 1: Infer trigger
        trigger = TriggerInferrer().execute({"description": desc})
        assert trigger.type == "schedule"

        # Step 2: Infer actions
        action_inferrer = ActionInferrer()
        actions = action_inferrer.infer_all({"description": desc})
        action_types = {a.type for a in actions}
        assert "email" in action_types

        # Step 3: Parse schedule
        schedule = ScheduleParser().execute({"description": desc})
        assert schedule.type in ("cron", "interval")

        # Step 4: Extract conditions
        conditions = ConditionExtractor().execute({"description": desc})
        assert len(conditions.conditions) > 0
        assert any("inventario" in c.lower() for c in conditions.conditions)

        # Step 5: Generate name
        name = AutomationNamer().execute({
            "trigger_spec": trigger,
            "action_spec": actions[0] if actions else None,
            "description": desc,
        })
        assert name.name != ""

        # Step 6: Serialize workflow
        workflow = WorkflowSerializer().execute({
            "trigger": trigger,
            "actions": actions,
            "schedule": schedule,
            "conditions": conditions,
            "name": name.name,
            "description": desc,
        })
        assert workflow.executable["name"] == name.name
        assert len(workflow.executable["actions"]) > 0

        # Verify JSON is valid
        parsed = json.loads(workflow.json_spec)
        assert parsed["name"] == name.name

    def test_full_automation_pipeline_en(self):
        """Full pipeline in English: 'Send alert notification every 2 hours if server error rate > 5%'"""
        desc = "Send alert notification every 2 hours if server error rate > 5%"

        # Step 1: Trigger (schedule keyword "every" detected)
        trigger = TriggerInferrer().execute({"description": desc})
        assert trigger.type == "schedule"

        # Step 2: Actions
        action_inferrer = ActionInferrer()
        actions = action_inferrer.infer_all({"description": desc})
        action_types = {a.type for a in actions}
        assert "notification" in action_types or "http" in action_types

        # Step 3: Schedule
        schedule = ScheduleParser().execute({"description": desc})
        assert schedule.type == "interval"
        assert schedule.interval_seconds == 2 * 3600

        # Step 4: Conditions
        conditions = ConditionExtractor().execute({"description": desc})
        assert len(conditions.conditions) > 0

        # Step 5: Name
        name = AutomationNamer().execute({"description": desc})
        assert name.name != ""

        # Step 6: Serialize
        workflow = WorkflowSerializer().execute({
            "trigger": trigger,
            "actions": actions,
            "schedule": schedule,
            "conditions": conditions,
            "name": name.name,
            "description": desc,
        })
        assert isinstance(workflow, WorkflowSpec)
        assert workflow.executable["name"] == name.name
