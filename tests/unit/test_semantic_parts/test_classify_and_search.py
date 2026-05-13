"""Tests for classify_intent (fallback and with embeddings), search, and find_similar_intents."""

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.core.semantic_engine import (
    SemanticEngine,
    SemanticResult,
    EMBEDDING_DIM,
)
from ._fixtures import engine, loaded_engine


# ===========================================================================
#  Test: classify_intent() - fallback
# ===========================================================================

class TestClassifyIntentFallback:
    """Tests for classify_intent fallback path (no model loaded)."""

    def test_fallback_returns_semantic_result(self, engine):
        result = engine.classify_intent("create a new module")
        assert isinstance(result, SemanticResult)
        assert result.source == "fallback"

    def test_fallback_detects_create(self, engine):
        result = engine.classify_intent("create a new module")
        assert result.operation == "CREATE"

    def test_fallback_detects_debug(self, engine):
        result = engine.classify_intent("fix the bug in my code")
        assert result.operation == "DEBUG"

    def test_fallback_confidence_below_threshold(self, engine):
        result = engine.classify_intent("something random xyz")
        assert result.confidence <= 0.5


# ===========================================================================
#  Test: classify_intent() - with embeddings
# ===========================================================================

class TestClassifyIntentWithEmbeddings:
    """Tests for classify_intent with mocked embeddings."""

    def test_returns_embedding_source(self, loaded_engine):
        query_emb = loaded_engine._prototype_embeddings["CREATE"].copy()
        loaded_engine._model.embed.return_value = iter([query_emb])
        loaded_engine._embed_cache.clear()
        result = loaded_engine.classify_intent("create something")
        assert result.source == "embedding"

    def test_returns_semantic_result(self, loaded_engine):
        query_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)
        loaded_engine._model.embed.return_value = iter([query_emb])
        loaded_engine._embed_cache.clear()
        result = loaded_engine.classify_intent("test query")
        assert isinstance(result, SemanticResult)
        assert 0.0 <= result.confidence <= 1.0


# ===========================================================================
#  Test: search()
# ===========================================================================

class TestSemanticSearch:
    """Tests for the search method."""

    def test_search_returns_empty_when_not_loaded(self, engine):
        result = engine.search("query", [{"text": "doc1"}])
        assert result == []

    def test_search_returns_empty_for_empty_docs(self, loaded_engine):
        result = loaded_engine.search("query", [])
        assert result == []

    def test_search_with_documents(self, loaded_engine):
        query_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)
        doc_emb = query_emb.copy()
        loaded_engine.embed = MagicMock(return_value=query_emb)
        loaded_engine.embed_batch = MagicMock(return_value=[doc_emb])
        docs = [{"text": "relevant doc"}]
        results = loaded_engine.search("relevant query", docs, top_k=5, threshold=0.1)
        assert len(results) >= 1
        assert results[0][1] > 0.9


# ===========================================================================
#  Test: find_similar_intents()
# ===========================================================================

class TestFindSimilarIntents:
    """Tests for the find_similar_intents method."""

    def test_returns_empty_when_not_loaded(self, engine):
        result = engine.find_similar_intents("query", ["hist1"])
        assert result == []

    def test_returns_empty_for_empty_history(self, loaded_engine):
        result = loaded_engine.find_similar_intents("query", [])
        assert result == []

    def test_finds_similar_history(self, loaded_engine):
        query_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)
        hist_emb = query_emb.copy()
        loaded_engine.embed = MagicMock(return_value=query_emb)
        loaded_engine.embed_batch = MagicMock(return_value=[hist_emb])
        results = loaded_engine.find_similar_intents("my query", ["my query"], threshold=0.1)
        assert len(results) >= 1
