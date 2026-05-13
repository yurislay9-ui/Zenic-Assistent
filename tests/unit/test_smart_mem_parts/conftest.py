"""Shared fixtures for SmartMemory tests."""

import os
import pytest
import numpy as np
from unittest.mock import MagicMock

from src.core.smart_memory import SmartMemory


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect SmartMemory DB to a temporary directory for isolation.

    After modularization, DB_PATH is imported by multiple sub-modules,
    so we must patch it in each module that references it.
    """
    tmp_db_dir = str(tmp_path / "smart_mem_test")
    os.makedirs(tmp_db_dir, exist_ok=True)
    tmp_db_path = os.path.join(tmp_db_dir, "smart_memory.sqlite")

    # Patch facade (src.core.smart_memory)
    monkeypatch.setattr("src.core.smart_memory.DB_DIR", tmp_db_dir)
    monkeypatch.setattr("src.core.smart_memory.DB_PATH", tmp_db_path)

    # Patch source-of-truth module (types.py)
    monkeypatch.setattr("src.core.memory_parts.types.DB_DIR", tmp_db_dir)
    monkeypatch.setattr("src.core.memory_parts.types.DB_PATH", tmp_db_path)

    # Patch all sub-modules that import DB_PATH / DB_DIR from types
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
