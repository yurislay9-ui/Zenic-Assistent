"""
Shared fixtures for test_scrap_parts sub-modules.
"""

import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _prevent_env_reload(monkeypatch):
    """Prevent real .env loading during tests."""
    try:
        import src.core.env_loader as env_mod
        monkeypatch.setattr(env_mod, '_loaded', True)
    except ImportError:
        pass
