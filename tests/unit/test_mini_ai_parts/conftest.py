"""Shared fixtures for mini AI engine tests."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.mini_ai_engine import MiniAIEngine, IntentResult, MODEL_PATH


@pytest.fixture
def engine_no_model():
    """Engine without model loaded (fallback mode)."""
    return MiniAIEngine(auto_load=False)


@pytest.fixture
def engine_with_model():
    """Engine with model if available, otherwise fallback mode."""
    if os.path.exists(MODEL_PATH):
        return MiniAIEngine(auto_load=True)
    pytest.skip("Model file not available for testing")
