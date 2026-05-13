"""Shared fixtures for automation agent tests."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.automation_agent import (
    AutomationAgent,
    TRIGGER_KEYWORDS,
    ACTION_KEYWORDS,
    SCHEDULE_PATTERNS,
)
from src.core.agents.schemas import (
    AutomationInput,
    AutomationOutput,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
)
from src.core.agents.base import AgentResult


@pytest.fixture
def agent():
    """AutomationAgent without external dependencies."""
    return AutomationAgent()


@pytest.fixture
def agent_with_memory():
    """AutomationAgent with mocked SmartMemory."""
    agent = AutomationAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory
