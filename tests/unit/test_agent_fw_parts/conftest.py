"""
Shared fixtures and test agent classes for test_agent_fw_parts sub-modules.
"""

import json
import pytest
from unittest.mock import MagicMock

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.runner import AgentRunner
from src.core.agents.cache import AgentCache
from src.core.agents.prompts import PromptBuilder, AgentPrompts
from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningOutput, ReasoningStep,
    BusinessInput, BusinessOutput,
    CodeInput, CodeOutput, FileSpec,
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
    ValidationInput, ValidationOutput, ValidationIssue,
)


class SampleAgent(BaseAgent):
    """Agente concreto de prueba."""

    def __init__(self):
        super().__init__(name="test_agent")

    def build_prompt(self, input_data):
        return (
            "You are a test agent. Reply with JSON.",
            f"Process: {input_data}"
        )

    def parse_response(self, raw_response, input_data):
        try:
            data = json.loads(raw_response)
            return IntentOutput(
                operation=data.get("operation", "SEARCH"),
                goal=data.get("goal", "FEATURE_ADD"),
                confidence=data.get("confidence", 0.5),
                source="llm",
            )
        except (json.JSONDecodeError, TypeError):
            return None

    def fallback(self, input_data):
        return IntentOutput(
            operation="SEARCH",
            goal="FEATURE_ADD",
            confidence=0.1,
            source="fallback",
        )


class BrokenAgent(BaseAgent):
    """Agente que siempre falla en parse_response."""

    def __init__(self):
        super().__init__(name="broken_agent")

    def build_prompt(self, input_data):
        return "system", "user"

    def parse_response(self, raw_response, input_data):
        return None  # Always fails

    def fallback(self, input_data):
        return IntentOutput(operation="SEARCH", source="fallback")
