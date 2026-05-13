"""Shared fixtures for resource governor tests."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.shared.resource_governor import (
    ResourceGovernor,
    get_governor,
    init_governor,
    tune_gc_for_arm,
    set_process_priority_low,
)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Reset ResourceGovernor singleton for each test."""
    try:
        import src.core.shared.resource_governor as rg_module
        monkeypatch.setattr(rg_module, '_governor', None, raising=False)
    except ImportError:
        pass
