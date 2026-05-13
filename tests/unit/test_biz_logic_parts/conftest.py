"""Shared fixtures for business_logic_agent tests."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.business_logic_agent import BusinessLogicAgent


@pytest.fixture
def agent():
    """BusinessLogicAgent without external dependencies (pure fallback mode)."""
    return BusinessLogicAgent()


@pytest.fixture
def agent_with_memory():
    """BusinessLogicAgent with mocked SmartMemory."""
    agent = BusinessLogicAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory
