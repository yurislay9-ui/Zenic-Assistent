"""
Shared fixtures for test_f4_f5_parts — also imported by facade.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent


@pytest.fixture
def code_agent():
    """CodeAgent without external dependencies (pure fallback mode)."""
    return CodeAgent()


@pytest.fixture
def automation_agent():
    """AutomationAgent without external dependencies (pure fallback mode)."""
    return AutomationAgent()


@pytest.fixture
def validation_agent():
    """ValidationAgent without external dependencies (pure fallback mode)."""
    return ValidationAgent()
