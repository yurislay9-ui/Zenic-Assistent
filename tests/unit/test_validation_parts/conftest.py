"""Shared fixtures for test_validation_parts."""

import pytest

from src.core.agents.validation_agent import ValidationAgent


@pytest.fixture
def agent():
    """ValidationAgent without external dependencies."""
    return ValidationAgent()
