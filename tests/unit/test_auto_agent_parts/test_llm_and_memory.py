"""Tests for LLM path and SmartMemory integration."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.schemas import (
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
)
from src.core.agents.base import AgentResult


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestAutomationLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_with_automation_input(self, agent):
        """Should build system + user prompt from AutomationInput."""
        system, user = agent.build_prompt(AutomationInput(
            description="send daily email report",
            context={"region": "US"},
        ))
        assert "automation" in system.lower()
        assert "send daily email report" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("automate report generation")
        assert "automation" in system.lower()

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '''{
            "name": "daily_report",
            "triggers": [{"type": "schedule", "config": {"interval": "daily"}, "description": "Daily trigger"}],
            "actions": [{"type": "email", "config": {"to": "admin@co.com"}, "description": "Send email"}],
            "schedule": {"type": "cron", "interval_seconds": 0, "cron_expression": "0 9 * * *", "description": "Daily at 9"},
            "conditions": [],
            "description": "Daily report"
        }'''
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.name == "daily_report"
        assert len(result.triggers) == 1
        assert result.triggers[0].type == "schedule"
        assert len(result.actions) == 1
        assert result.actions[0].type == "email"
        assert result.source == "llm"

    def test_parse_response_free_text(self, agent):
        """Should parse free text when no JSON is found."""
        raw = "This automation should send a daily email report"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.source == "llm"

    def test_parse_response_empty(self, agent):
        """Should return None for very short/empty text."""
        result = agent.parse_response("short", None)
        assert result is None


# ============================================================
#  Test: SmartMemory Integration
# ============================================================

class TestAutomationSmartMemory:
    """Tests for SmartMemory cache integration."""

    def test_smart_memory_cache_hit(self, agent_with_memory):
        """Should return cached result from SmartMemory."""
        agent, mock_memory = agent_with_memory
        mock_memory.check_cache.return_value = {
            "response": '{"name":"cached_auto","triggers":[{"type":"manual","config":{},"description":""}],"actions":[{"type":"log","config":{},"description":""}],"schedule":{"type":"manual","interval_seconds":0,"cron_expression":"","description":""},"conditions":[],"description":"cached"}',
        }
        result = agent.fallback(AutomationInput(description="daily report"))
        assert result.name == "cached_auto"
        assert result.source == "fallback"

    def test_smart_memory_save_on_result(self, agent_with_memory):
        """Should save result to SmartMemory after fallback."""
        agent, mock_memory = agent_with_memory
        agent.fallback(AutomationInput(description="daily report"))
        assert mock_memory.save_to_cache.called

    def test_smart_memory_failure_graceful(self, agent):
        """Should handle SmartMemory failures gracefully."""
        mock_memory = MagicMock()
        mock_memory.check_cache.side_effect = Exception("DB error")
        mock_memory.save_to_cache.side_effect = Exception("DB error")
        agent.wire(smart_memory=mock_memory)
        result = agent.fallback(AutomationInput(description="daily report"))
        assert result is not None
