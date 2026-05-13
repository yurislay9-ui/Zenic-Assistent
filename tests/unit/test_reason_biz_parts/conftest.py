"""Shared fixtures for test_reason_biz_parts."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.reasoning_agent import ReasoningAgent


@pytest.fixture
def reasoning_agent():
    return ReasoningAgent()


@pytest.fixture
def reasoning_agent_with_memory():
    agent = ReasoningAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    mock_memory.get_working_context.return_value = ""
    mock_memory.find_similar_solutions.return_value = []
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory
