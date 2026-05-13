"""Shared fixtures for test_surgical_parts."""

import pytest
from unittest.mock import MagicMock

from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.schemas import IntentInput


@pytest.fixture
def agent():
    """SurgicalAgent without external dependencies (pure fallback mode)."""
    return SurgicalAgent()


@pytest.fixture
def agent_with_semantic():
    """SurgicalAgent with mocked SemanticEngine."""
    agent = SurgicalAgent()
    mock_semantic = MagicMock()
    mock_semantic.is_loaded = True
    mock_semantic.classify_intent.return_value = MagicMock(
        operation="CREATE",
        goal="FEATURE_ADD",
        confidence=0.85,
        source="embedding",
    )
    agent.wire(semantic_engine=mock_semantic)
    return agent, mock_semantic


@pytest.fixture
def agent_with_memory():
    """SurgicalAgent with mocked SmartMemory."""
    agent = SurgicalAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


@pytest.fixture
def agent_full():
    """SurgicalAgent with both SemanticEngine and SmartMemory."""
    agent = SurgicalAgent()
    mock_semantic = MagicMock()
    mock_semantic.is_loaded = True
    mock_semantic.classify_intent.return_value = MagicMock(
        operation="CREATE", goal="FEATURE_ADD",
        confidence=0.85, source="embedding",
    )
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(semantic_engine=mock_semantic, smart_memory=mock_memory)
    return agent, mock_semantic, mock_memory
