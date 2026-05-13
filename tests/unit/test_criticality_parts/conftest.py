"""Shared fixtures for test_criticality_parts."""

import pytest

from src.core.agents.criticality_agent import CriticalityAgent


@pytest.fixture
def agent():
    """CriticalityAgent without external dependencies."""
    return CriticalityAgent()


@pytest.fixture
def agent_with_history():
    """CriticalityAgent with pre-populated history."""
    agent = CriticalityAgent()
    agent._history = [
        {"op": "DELETE", "goal": "SECURITY_HARDEN", "target": "auth.py", "level": 3},
        {"op": "CREATE", "goal": "FEATURE_ADD", "target": "utils.py", "level": 1},
        {"op": "REFACTOR", "goal": "BUG_FIX", "target": "auth.py", "level": 3},
    ]
    return agent
