"""
Unit tests for SmartMemory

Tests initialization, episodic memory, procedural memory, working memory,
semantic cache, thread safety, and utility methods.
"""

import os
import numpy as np
import pytest
from unittest.mock import MagicMock

from src.core.smart_memory import SmartMemory


# ============================================================
#  Fixtures (also in test_smart_mem_parts/conftest.py for direct sub-module runs)
# ============================================================

@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect SmartMemory DB to a temporary directory for isolation."""
    tmp_db_dir = str(tmp_path / "smart_mem_test")
    os.makedirs(tmp_db_dir, exist_ok=True)
    tmp_db_path = os.path.join(tmp_db_dir, "smart_memory.sqlite")

    monkeypatch.setattr("src.core.smart_memory.DB_DIR", tmp_db_dir)
    monkeypatch.setattr("src.core.smart_memory.DB_PATH", tmp_db_path)
    monkeypatch.setattr("src.core.memory_parts.types.DB_DIR", tmp_db_dir)
    monkeypatch.setattr("src.core.memory_parts.types.DB_PATH", tmp_db_path)
    monkeypatch.setattr("src.core.memory_parts.database.DB_PATH", tmp_db_path)
    monkeypatch.setattr("src.core.memory_parts.cache.DB_PATH", tmp_db_path)
    monkeypatch.setattr("src.core.memory_parts.longterm.DB_PATH", tmp_db_path)
    monkeypatch.setattr("src.core.memory_parts.episodes.DB_PATH", tmp_db_path)
    monkeypatch.setattr("src.core.memory_parts.memory.DB_DIR", tmp_db_dir)
    monkeypatch.setattr("src.core.memory_parts.memory.DB_PATH", tmp_db_path)

    yield tmp_db_path


@pytest.fixture
def memory():
    """Create a SmartMemory instance with no semantic engine (fallback mode)."""
    return SmartMemory(semantic_engine=None)


@pytest.fixture
def memory_with_semantic():
    """Create a SmartMemory with a mocked semantic engine."""
    sem = MagicMock()
    sem.is_loaded = True
    dummy_emb = np.random.randn(384).astype(np.float32)
    dummy_emb = dummy_emb / np.linalg.norm(dummy_emb)
    sem.embed.return_value = dummy_emb
    sem.similarity.return_value = 0.9
    mem = SmartMemory(semantic_engine=sem)
    return mem


from .test_smart_mem_parts import *  # noqa: F401,F403
