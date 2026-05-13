"""Tests for legacy compatibility, wire, and stats."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.schemas import (
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
)
from src.core.agents.base import AgentResult


# ============================================================
#  Test: Legacy Compatibility
# ============================================================

class TestAutomationLegacyCompat:
    """Tests for to_workflow_dict() legacy compatibility."""

    def test_to_workflow_dict(self, agent):
        """Should convert AutomationOutput to workflow dict."""
        output = AutomationOutput(
            name="daily_report",
            triggers=[TriggerSpec(type="schedule", config={"interval": "daily"})],
            actions=[ActionSpec(type="email", config={"to": "admin@co.com"}, description="Send email")],
            schedule=ScheduleSpec(type="cron", cron_expression="0 9 * * *"),
            conditions=["if sales > 1000"],
            description="Daily report automation",
        )
        result = agent.to_workflow_dict(output)
        assert result["name"] == "daily_report"
        assert result["trigger"]["type"] == "schedule"
        assert len(result["actions"]) == 1
        assert result["actions"][0]["type"] == "email"
        assert result["schedule"]["cron_expression"] == "0 9 * * *"
        assert "if sales > 1000" in result["conditions"]

    def test_to_workflow_dict_empty_triggers(self, agent):
        """Should handle empty triggers gracefully."""
        output = AutomationOutput(name="test", triggers=[], actions=[])
        result = agent.to_workflow_dict(output)
        assert result["trigger"]["type"] == "schedule"  # default


# ============================================================
#  Test: Wire and Stats
# ============================================================

class TestAutomationWireAndStats:
    """Tests for wire() and stats tracking."""

    def test_wire_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        assert agent._semantic_engine is mock_se

    def test_wire_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_mem = MagicMock()
        agent.wire(smart_memory=mock_mem)
        assert agent._smart_memory is mock_mem

    def test_stats_after_fallback(self, agent):
        """Should track fallback calls in stats."""
        agent.fallback(AutomationInput(description="daily report"))
        stats = agent.stats
        assert stats["name"] == "automation"
        assert stats["total_calls"] >= 1

    def test_design_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = AutomationOutput(
            name="llm_auto", source="llm",
            triggers=[TriggerSpec(type="schedule")],
            actions=[ActionSpec(type="log")],
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.design_with_runner(mock_runner, "daily report")
        assert result.name == "llm_auto"
        assert result.source == "llm"

    def test_design_with_runner_failure_falls_back(self, agent):
        """Should fall back when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        result = agent.design_with_runner(mock_runner, "daily report")
        assert result.source == "fallback"
