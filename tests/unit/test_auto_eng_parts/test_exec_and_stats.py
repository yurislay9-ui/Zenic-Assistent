"""Tests for workflow execution, management, trigger/action inference, and stats."""

import pytest
from unittest.mock import MagicMock

from src.core.automation_engine import (
    AutomationEngine, Workflow, Trigger, Action, TriggerType, ActionType,
)
from ._fixtures import temp_db, engine, sample_workflow


class TestWorkflowExecution:
    """Tests for workflow execution."""

    def test_execute_nonexistent_workflow(self, engine):
        """Executing a nonexistent workflow should return error."""
        result = engine._execute_workflow_sync("nonexistent_id")
        assert result.status == "failed"
        assert "not found" in result.error.lower()

    def test_execute_disabled_workflow(self, engine):
        """Executing a disabled workflow should return error."""
        wf = engine.create_workflow(name="Disabled Test")
        wf.enabled = False
        result = engine._execute_workflow_sync(wf.id)
        assert result.status == "failed"
        assert "disabled" in result.error.lower()

    def test_execute_workflow_sync_success(self, engine, sample_workflow):
        """Sync execution with no executor_registry should use legacy stubs."""
        result = engine._execute_workflow_sync(sample_workflow.id)
        assert result.status in ("success", "partial")
        assert result.started_at > 0
        assert result.finished_at >= result.started_at

    def test_execute_updates_run_count(self, engine, sample_workflow):
        """Execution should increment the workflow's run_count."""
        initial_count = sample_workflow.run_count
        engine._execute_workflow_sync(sample_workflow.id)
        assert sample_workflow.run_count == initial_count + 1

    def test_execute_with_executor_registry(self, engine, sample_workflow):
        """When executor_registry is available, it should be used."""
        mock_registry = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.duration_ms = 100.0
        mock_result.error = ""
        mock_registry.execute_action = MagicMock(return_value=mock_result)
        engine._executor_registry = mock_registry
        result = engine._execute_workflow_sync(sample_workflow.id)
        assert result.actions_executed > 0

    def test_execute_with_executor_failure(self, engine, sample_workflow):
        """When executor fails, action should be counted as failed."""
        mock_registry = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.duration_ms = 50.0
        mock_result.error = "Connection refused"
        mock_registry.execute_action = MagicMock(return_value=mock_result)
        engine._executor_registry = mock_registry
        result = engine._execute_workflow_sync(sample_workflow.id)
        assert result.actions_failed > 0

    def test_execute_logs_execution(self, engine, sample_workflow, temp_db):
        """Execution should be logged to the execution_log table."""
        engine._execute_workflow_sync(sample_workflow.id)
        history = engine.get_execution_history(sample_workflow.id)
        assert len(history) >= 1


class TestWorkflowManagement:
    """Tests for listing, toggling, and deleting workflows."""

    def test_list_workflows(self, engine, sample_workflow):
        workflows = engine.list_workflows()
        assert len(workflows) >= 1
        assert any(w["name"] == "Daily Sales Report" for w in workflows)

    def test_get_workflow(self, engine, sample_workflow):
        result = engine.get_workflow(sample_workflow.id)
        assert result is not None
        assert result["name"] == "Daily Sales Report"

    def test_get_nonexistent_workflow(self, engine):
        result = engine.get_workflow("nonexistent")
        assert result is None

    def test_toggle_workflow(self, engine, sample_workflow):
        assert sample_workflow.enabled is True
        new_state = engine.toggle_workflow(sample_workflow.id)
        assert new_state is False
        assert sample_workflow.status == "paused"
        new_state = engine.toggle_workflow(sample_workflow.id)
        assert new_state is True
        assert sample_workflow.status == "active"

    def test_toggle_nonexistent_workflow(self, engine):
        result = engine.toggle_workflow("nonexistent")
        assert result is False

    def test_delete_workflow(self, engine, sample_workflow):
        wf_id = sample_workflow.id
        result = engine.delete_workflow(wf_id)
        assert result is True
        assert wf_id not in engine._workflows

    def test_delete_nonexistent_workflow(self, engine):
        result = engine.delete_workflow("nonexistent")
        assert result is False


class TestTriggerActionInference:
    """Tests for trigger and action inference from descriptions."""

    def test_infer_schedule_daily(self, engine):
        trigger = engine._infer_trigger("Enviar reporte diario cada dia")
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config["interval"] == "daily"

    def test_infer_schedule_weekly(self, engine):
        trigger = engine._infer_trigger("Enviar reporte semanal cada lunes")
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config["interval"] == "weekly"

    def test_infer_schedule_monthly(self, engine):
        trigger = engine._infer_trigger("Enviar reporte mensual")
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config["interval"] == "monthly"

    def test_infer_event(self, engine):
        trigger = engine._infer_trigger("Cuando el stock baje de 5 unidades")
        assert trigger.type == TriggerType.EVENT

    def test_infer_webhook(self, engine):
        trigger = engine._infer_trigger("Recibir datos via webhook callback")
        assert trigger.type == TriggerType.WEBHOOK

    def test_infer_actions_email(self, engine):
        actions = engine._infer_actions("Enviar correo con el reporte")
        assert any(a.type == ActionType.SEND_EMAIL for a in actions)

    def test_infer_actions_report(self, engine):
        actions = engine._infer_actions("Generar reporte de ventas")
        assert any(a.type == ActionType.GENERATE_REPORT for a in actions)

    def test_infer_actions_backup(self, engine):
        actions = engine._infer_actions("Backup de la base de datos")
        assert any(a.type == ActionType.DATABASE_OPERATION for a in actions)

    def test_infer_actions_notification(self, engine):
        actions = engine._infer_actions("Notificar cuando haya error")
        assert any(a.type == ActionType.SEND_NOTIFICATION for a in actions)

    def test_infer_actions_default_notification(self, engine):
        actions = engine._infer_actions("Do something random xyz")
        assert len(actions) >= 1
        assert any(a.type == ActionType.SEND_NOTIFICATION for a in actions)

    def test_infer_actions_data_sync(self, engine):
        actions = engine._infer_actions("Sincronizar datos del CRM")
        assert any(a.type == ActionType.DATA_SYNC for a in actions)

    def test_extract_name(self, engine):
        name = engine._extract_name("Enviar reporte semanal por email")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_extract_name_empty_description(self, engine):
        name = engine._extract_name("")
        assert name == "automation"


class TestAutomationStats:
    """Tests for stats reporting."""

    def test_stats_initial(self, engine):
        stats = engine.stats
        assert stats["total_workflows"] == 0
        assert stats["active_workflows"] == 0

    def test_stats_after_creation(self, engine, sample_workflow):
        stats = engine.stats
        assert stats["total_workflows"] >= 1
        assert stats["active_workflows"] >= 1

    def test_stats_after_execution(self, engine, sample_workflow):
        engine._execute_workflow_sync(sample_workflow.id)
        stats = engine.stats
        assert stats["total_executions"] >= 1
