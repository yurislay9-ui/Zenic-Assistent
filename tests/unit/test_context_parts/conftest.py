"""Shared fixtures for test_context_parts."""

import pytest
import time
from unittest.mock import MagicMock

from src.core.agents.context_agent import (
    ContextAgent,
    ContextOutput,
    ContextEntry,
)
from src.core.agents.schemas import IntentOutput


@pytest.fixture
def mock_smart_memory():
    """SmartMemory mock con working memory poblada."""
    mem = MagicMock()

    # Working memory entries
    entries = []
    for i, (op, goal, q, resp) in enumerate([
        ("CREATE", "FEATURE_ADD", "build REST API", "FastAPI code"),
        ("DEBUG", "BUG_FIX", "fix SQL injection", "Used whitelist"),
        ("OPTIMIZE", "PERFORMANCE", "optimize queries", "Added indexes"),
        ("REFACTOR", "COMPLEXITY_REDUCTION", "simplify parser", "Reduced 200 lines"),
        ("SEARCH", "FEATURE_ADD", "find auth module", "Found auth_service.py"),
    ]):
        entry = MagicMock()
        entry.operation = op
        entry.goal = goal
        entry.query = q
        entry.response = resp
        entry.importance = 0.5 + i * 0.1
        entry.timestamp = time.time() - (i * 60)
        entry.session_id = "test123"
        entries.append(entry)

    mem._working_memory = entries

    # Mock methods
    mem.check_cache.return_value = None
    mem.get_working_context.return_value = "Previous: CREATE/FEATURE_ADD → FastAPI code"
    mem.find_similar_solutions.return_value = [
        {"query": "build API", "solution": "Used FastAPI", "operation": "CREATE",
         "goal": "FEATURE_ADD", "importance": 0.7, "similarity": 0.85}
    ]
    mem.find_patterns.return_value = [
        {"pattern_name": "api_pattern", "pattern_type": "strategy",
         "description": "REST API with FastAPI", "success_rate": 0.8}
    ]
    mem.find_episodes.return_value = []

    return mem


@pytest.fixture
def mock_semantic_engine():
    """SemanticEngine mock."""
    sem = MagicMock()
    sem.is_loaded = True
    return sem


@pytest.fixture
def context_agent(mock_semantic_engine, mock_smart_memory):
    """ContextAgent con dependencias mockeadas."""
    return ContextAgent(
        semantic_engine=mock_semantic_engine,
        smart_memory=mock_smart_memory,
    )


@pytest.fixture
def sample_intent_output():
    """IntentOutput de ejemplo."""
    return IntentOutput(
        operation="CREATE",
        goal="FEATURE_ADD",
        target="api.py",
        language="python",
        confidence=0.85,
        source="tfidf",
    )
