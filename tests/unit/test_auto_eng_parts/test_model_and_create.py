"""Tests for workflow data model and creation."""

import pytest
from src.core.automation_engine import (
    Workflow, Trigger, Action, TriggerType, ActionType,
)
from ._fixtures import temp_db, engine, sample_workflow


class TestWorkflowDataModel:
    """Tests for Workflow, Trigger, Action dataclasses."""

    def test_trigger_defaults(self):
        trigger = Trigger()
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config == {}

    def test_action_defaults(self):
        action = Action()
        assert action.type == ActionType.SEND_NOTIFICATION
        assert action.config == {}

    def test_workflow_defaults(self):
        wf = Workflow()
        assert wf.id == ""
        assert wf.name == ""
        assert wf.enabled is True
        assert wf.status == "active"
        assert wf.run_count == 0

    def test_trigger_type_enum(self):
        assert TriggerType.SCHEDULE.value == "schedule"
        assert TriggerType.EVENT.value == "event"
        assert TriggerType.WEBHOOK.value == "webhook"
        assert TriggerType.FILE_CHANGE.value == "file_change"
        assert TriggerType.DATA_CHANGE.value == "data_change"

    def test_action_type_enum(self):
        assert ActionType.SEND_EMAIL.value == "send_email"
        assert ActionType.RUN_SCRIPT.value == "run_script"
        assert ActionType.GENERATE_REPORT.value == "generate_report"
        assert ActionType.DATA_SYNC.value == "data_sync"


class TestWorkflowCreation:
    """Tests for creating workflows."""

    def test_create_workflow_basic(self, engine):
        """create_workflow should return a Workflow with an ID."""
        wf = engine.create_workflow(name="Test Workflow")
        assert wf.id != ""
        assert wf.name == "Test Workflow"
        assert wf.created_at > 0
        assert wf.enabled is True

    def test_create_workflow_with_trigger_and_actions(self, engine):
        """create_workflow should preserve trigger and actions."""
        trigger = Trigger(type=TriggerType.EVENT, config={"event_type": "stock_low"})
        actions = [Action(type=ActionType.SEND_NOTIFICATION, config={"message": "Low stock"})]
        wf = engine.create_workflow(
            name="Stock Alert",
            trigger=trigger,
            actions=actions,
        )
        assert wf.trigger.type == TriggerType.EVENT
        assert len(wf.actions) == 1
        assert wf.actions[0].type == ActionType.SEND_NOTIFICATION

    def test_create_workflow_stored_in_engine(self, engine):
        """Created workflow should be stored in the engine's dict."""
        wf = engine.create_workflow(name="Stored Test")
        assert wf.id in engine._workflows

    def test_create_from_description_email(self, engine):
        """create_from_description should detect email patterns."""
        wf = engine.create_from_description("Enviar reporte semanal por email cada lunes")
        assert wf.name != ""
        assert len(wf.actions) > 0
        action_types = [a.type for a in wf.actions]
        assert ActionType.SEND_EMAIL in action_types

    def test_create_from_description_schedule(self, engine):
        """create_from_description should detect schedule keywords."""
        wf = engine.create_from_description("Backup diario de la base de datos")
        assert wf.trigger.type == TriggerType.SCHEDULE

    def test_create_from_description_event(self, engine):
        """create_from_description should detect event keywords."""
        wf = engine.create_from_description("Cuando se agote el stock, notificar")
        assert wf.trigger.type == TriggerType.EVENT

    def test_create_from_description_webhook(self, engine):
        """create_from_description should detect webhook keywords."""
        wf = engine.create_from_description("Recibir notificaciones via webhook endpoint")
        assert wf.trigger.type == TriggerType.WEBHOOK
