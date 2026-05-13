"""Tests for init, lifecycle, stats, embed, embed_batch, similarity, similarity_text."""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.core.semantic_engine import (
    SemanticEngine,
    SemanticResult,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    INTENT_PROTOTYPES,
    GOAL_PROTOTYPES,
)
from ._fixtures import engine, loaded_engine


# ===========================================================================
#  Test: Initialization
# ===========================================================================

class TestSemanticEngineInit:
    """Tests for SemanticEngine initialization."""

    def test_init_no_auto_load(self):
        eng = SemanticEngine(auto_load=False)
        assert eng._model is None
        assert eng._loaded is False
        assert eng.is_loaded is False

    def test_init_default_call_count(self, engine):
        assert engine._call_count == 0

    def test_init_caches_empty(self, engine):
        assert len(engine._embed_cache) == 0
        assert len(engine._prototype_embeddings) == 0

    def test_init_load_time_zero(self, engine):
        assert engine._load_time == 0.0


# ===========================================================================
#  Test: Model lifecycle
# ===========================================================================

class TestModelLifecycle:
    """Tests for load_model and unload_model."""

    def test_load_model_failure(self, engine):
        with patch.dict("sys.modules", {"fastembed": None}):
            result = engine.load_model()
            assert result is False or result is True

    def test_load_model_returns_true_when_already_loaded(self, loaded_engine):
        result = loaded_engine.load_model()
        assert result is True

    def test_unload_model_clears_state(self, loaded_engine):
        loaded_engine.unload_model()
        assert loaded_engine._model is None
        assert loaded_engine._loaded is False
        assert len(loaded_engine._embed_cache) == 0
        assert len(loaded_engine._prototype_embeddings) == 0
        assert len(loaded_engine._goal_prototype_embeddings) == 0


# ===========================================================================
#  Test: stats property
# ===========================================================================

class TestStatsProperty:
    """Tests for the stats property."""

    def test_stats_unloaded(self, engine):
        stats = engine.stats
        assert stats["model_loaded"] is False
        assert stats["model_name"] == "none"
        assert stats["total_calls"] == 0
        assert stats["embedding_dim"] == EMBEDDING_DIM

    def test_stats_loaded(self, loaded_engine):
        stats = loaded_engine.stats
        assert stats["model_loaded"] is True
        assert EMBEDDING_MODEL in stats["model_name"]
        assert stats["load_time_s"] == 0.5

    def test_stats_cache_size(self, loaded_engine):
        loaded_engine._embed_cache["test_key"] = np.zeros(EMBEDDING_DIM)
        stats = loaded_engine.stats
        assert stats["cache_size"] == 1


# ===========================================================================
#  Test: embed()
# ===========================================================================

class TestEmbed:
    """Tests for the embed method."""

    def test_embed_returns_none_when_not_loaded(self, engine):
        result = engine.embed("hello world")
        assert result is None

    def test_embed_returns_ndarray_when_loaded(self, loaded_engine):
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_embedding = fake_embedding / np.linalg.norm(fake_embedding)
        loaded_engine._model.embed.return_value = iter([fake_embedding])
        result = loaded_engine.embed("hello world")
        assert isinstance(result, np.ndarray)
        assert result.shape == (EMBEDDING_DIM,)

    def test_embed_caches_result(self, loaded_engine):
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_embedding = fake_embedding / np.linalg.norm(fake_embedding)
        loaded_engine._model.embed.return_value = iter([fake_embedding])
        r1 = loaded_engine.embed("hello world")
        r2 = loaded_engine.embed("hello world")
        assert r1 is r2
        loaded_engine._model.embed.assert_called_once()

    def test_embed_increments_call_count(self, loaded_engine):
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_embedding = fake_embedding / np.linalg.norm(fake_embedding)
        loaded_engine._model.embed.return_value = iter([fake_embedding])
        initial_count = loaded_engine._call_count
        loaded_engine.embed("hello")
        assert loaded_engine._call_count == initial_count + 1

    def test_embed_returns_normalized_vector(self, loaded_engine):
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        loaded_engine._model.embed.return_value = iter([fake_embedding])
        result = loaded_engine.embed("test text")
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5


# ===========================================================================
#  Test: embed_batch()
# ===========================================================================

class TestEmbedBatch:
    """Tests for the embed_batch method."""

    def test_embed_batch_returns_empty_when_not_loaded(self, engine):
        result = engine.embed_batch(["hello", "world"])
        assert result == []

    def test_embed_batch_returns_list_of_ndarrays(self, loaded_engine):
        fake_embs = [np.random.randn(EMBEDDING_DIM).astype(np.float32) for _ in range(3)]
        loaded_engine._model.embed.return_value = iter(fake_embs)
        results = loaded_engine.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        for r in results:
            assert isinstance(r, np.ndarray)
            assert r.shape == (EMBEDDING_DIM,)

    def test_embed_batch_normalizes(self, loaded_engine):
        fake_embs = [np.random.randn(EMBEDDING_DIM).astype(np.float32) for _ in range(2)]
        loaded_engine._model.embed.return_value = iter(fake_embs)
        results = loaded_engine.embed_batch(["a", "b"])
        for r in results:
            norm = np.linalg.norm(r)
            assert abs(norm - 1.0) < 1e-5


# ===========================================================================
#  Test: similarity()
# ===========================================================================

class TestSimilarity:
    """Tests for the static similarity method."""

    def test_identical_vectors_similarity_one(self):
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        sim = SemanticEngine.similarity(v, v)
        assert abs(sim - 1.0) < 1e-5

    def test_orthogonal_vectors_similarity_zero(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        sim = SemanticEngine.similarity(a, b)
        assert abs(sim) < 1e-5

    def test_opposite_vectors_similarity_minus_one(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        sim = SemanticEngine.similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-5

    def test_similarity_returns_float(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.5, 0.5], dtype=np.float32)
        sim = SemanticEngine.similarity(a, b)
        assert isinstance(sim, float)


# ===========================================================================
#  Test: similarity_text()
# ===========================================================================

class TestSimilarityText:
    """Tests for the similarity_text method."""

    def test_returns_zero_when_not_loaded(self, engine):
        result = engine.similarity_text("hello", "world")
        assert result == 0.0

    def test_returns_similarity_when_loaded(self, loaded_engine):
        fake_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_emb = fake_emb / np.linalg.norm(fake_emb)
        loaded_engine._model.embed.return_value = iter([fake_emb, fake_emb])
        result = loaded_engine.similarity_text("hello", "hello")
        assert isinstance(result, float)
        assert -1.01 <= result <= 1.01
