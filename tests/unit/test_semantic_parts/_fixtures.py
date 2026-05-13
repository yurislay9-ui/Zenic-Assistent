"""Shared fixtures for semantic engine tests — imported into test files."""

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.core.semantic_engine import (
    SemanticEngine,
    SemanticResult,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    INTENT_PROTOTYPES,
    GOAL_PROTOTYPES,
)


@pytest.fixture
def engine():
    """SemanticEngine without auto_load (no real model)."""
    return SemanticEngine(auto_load=False)


@pytest.fixture
def loaded_engine():
    """SemanticEngine with a mocked loaded model."""
    eng = SemanticEngine(auto_load=False)
    eng._model = MagicMock()
    eng._loaded = True
    eng._load_time = 0.5

    for intent in INTENT_PROTOTYPES:
        emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        eng._prototype_embeddings[intent] = emb

    for goal in GOAL_PROTOTYPES:
        emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        eng._goal_prototype_embeddings[goal] = emb

    return eng
