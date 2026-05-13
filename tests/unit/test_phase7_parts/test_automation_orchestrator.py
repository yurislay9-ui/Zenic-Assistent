"""
Tests for Phase 7 AutomationEngine integration and Orchestrator integration.
"""

import pytest


# ============================================================
#  AUTOMATION ENGINE INTEGRATION TESTS
# ============================================================

class TestAutomationEngineIntegration:
    """Tests for AutomationEngine with real ActionExecutors."""

    def setup_method(self):
        from src.core.automation_engine import AutomationEngine
        from src.core.action_executor import get_default_registry
        self.engine = AutomationEngine(executor_registry=get_default_registry())

    def test_engine_has_executor_registry(self):
        """Engine should have executor registry initialized."""
        assert self.engine._executor_registry is not None

    def test_create_workflow(self):
        """Should create a workflow with actions."""
        from src.core.automation_engine import Trigger, TriggerType, Action, ActionType
        wf = self.engine.create_workflow(
            "Test Workflow",
            "Test description",
            trigger=Trigger(type=TriggerType.SCHEDULE, config={"interval": "daily", "hour": 9}),
            actions=[
                Action(type=ActionType.SEND_NOTIFICATION, config={"channel": "log", "message": "Test"}),
            ]
        )
        assert wf.name == "Test Workflow"
        assert len(wf.actions) == 1

    @pytest.mark.asyncio
    async def test_execute_workflow_with_notification(self):
        """Should execute workflow with real notification action."""
        from src.core.automation_engine import Trigger, TriggerType, Action, ActionType
        wf = self.engine.create_workflow(
            "Notification Test",
            "Test notification",
            trigger=Trigger(type=TriggerType.SCHEDULE, config={"interval": "daily"}),
            actions=[
                Action(type=ActionType.SEND_NOTIFICATION, config={"channel": "log", "message": "Integration test"}),
            ]
        )
        execution = await self.engine._execute_workflow_async(wf.id)
        assert execution.status in ("success", "partial")
        assert execution.actions_executed >= 1


# ============================================================
#  ORCHESTRATOR INTEGRATION TESTS
# ============================================================

class TestOrchestratorPhase7:
    """Tests for Orchestrator with Phase 7 engines."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.core.orchestrator import ZenicOrchestrator
        self.orch = ZenicOrchestrator()

    @pytest.mark.asyncio
    async def test_system_status_has_phase7(self):
        """System status should include Phase 7 engines."""
        status = await self.orch.get_system_status()
        assert "phase7_engines" in status
        assert status["phase7_engines"]["action_executors"] > 0
        assert status["phase7_engines"]["logic_blocks"] > 0
        assert status["phase7_engines"]["auth_available"] is True

    @pytest.mark.asyncio
    async def test_execute_action_endpoint(self):
        """execute_action endpoint should work."""
        result = await self.orch.execute_action(
            "send_notification",
            {"channel": "log", "message": "Orchestrator test"}
        )
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_build_logic_endpoint(self):
        """build_logic endpoint should compose blocks."""
        result = await self.orch.build_logic("sistema de inventario con alertas")
        assert result.get("block_count", 0) > 0
        assert "generated_code" in result

    @pytest.mark.asyncio
    async def test_list_logic_blocks_endpoint(self):
        """list_logic_blocks endpoint should return available blocks."""
        blocks = await self.orch.list_logic_blocks("business_logic")
        assert len(blocks) > 0
        assert all(b["category"] == "business_logic" for b in blocks)
