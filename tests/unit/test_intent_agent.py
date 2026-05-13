"""
Unit tests for IntentAgent (Phase F2)

Tests the unified intent classification agent that replaces
SemanticParser + SemanticEngine + MiniAIEngine classify_intent.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.intent_agent import IntentAgent


# ============================================================
#  Fixtures (also in test_intent_parts/conftest.py for direct sub-module runs)
# ============================================================

@pytest.fixture
def agent():
    """IntentAgent without external dependencies (pure fallback mode)."""
    return IntentAgent()


@pytest.fixture
def agent_with_semantic():
    """IntentAgent with mocked SemanticEngine."""
    agent = IntentAgent()
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
    """IntentAgent with mocked SmartMemory."""
    agent = IntentAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


from .test_intent_parts import *  # noqa: F401,F403
