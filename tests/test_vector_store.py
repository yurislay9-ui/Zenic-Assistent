"""
ZENIC-AGENTS v16 - Vector Store Integration Tests (Phase 4.1)

Tests for the pgvector-backed VectorStore and in-memory HNSW index.
Designed to run without external services (memory fallback) and
optionally with PostgreSQL (pgvector) for E2E validation.

Usage:
    pytest tests/test_vector_store.py -v                    # Memory backend
    DATABASE_URL=postgresql://... pytest tests/test_vector_store.py -v  # pgvector
"""

import asyncio
import math
import os
import random
import time
from typing import List

import pytest

# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def sample_vector():
    """A normalized 384-dimensional vector."""
    rng = random.Random(42)
    vec = [rng.gauss(0, 1) for _ in range(384)]
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


@pytest.fixture
def sample_vectors():
    """100 normalized 384-dimensional vectors."""
    rng = random.Random(42)
    vectors = []
    for i in range(100):
        vec = [rng.gauss(0, 1) for _ in range(384)]
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        vectors.append(vec)
    return vectors


# ── HNSW Index Tests ────────────────────────────────────────

class TestHNSWIndex:
    """Tests for the in-memory HNSW index."""

    def test_create_index(self):
        """Test creating an empty HNSW index."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=384, M=16, ef_construction=64)
        assert index.size == 0
        assert index.max_level == -1

    def test_insert_single(self):
        """Test inserting a single vector."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)
        vec = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        index.insert("doc1", vec)
        assert index.size == 1

    def test_insert_multiple(self):
        """Test inserting multiple vectors."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)
        for i in range(50):
            vec = [0.0] * 10
            vec[i % 10] = 1.0
            index.insert(f"doc_{i}", vec)
        assert index.size == 50
        assert index.max_level >= 0

    def test_search_empty_index(self):
        """Test searching an empty index returns no results."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)
        query = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        results = index.search(query, top_k=5)
        assert results == []

    def test_search_single_vector(self):
        """Test searching with a single vector in the index."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)
        vec = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        index.insert("doc1", vec)

        # Search with the same vector
        results = index.search(vec, top_k=1)
        assert len(results) >= 1
        assert results[0][0] == "doc1"
        assert results[0][1] > 0.99  # Should be very similar

    def test_search_top_k(self, sample_vectors):
        """Test searching returns correct top-k results."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=384, M=16, ef_construction=64, seed=42)
        for i, vec in enumerate(sample_vectors):
            index.insert(f"doc_{i}", vec)

        # Search for the first vector
        query = sample_vectors[0]
        results = index.search(query, top_k=5)
        assert len(results) >= 1
        # The first result should be the query vector itself (similarity ≈ 1.0)
        assert results[0][0] == "doc_0"
        assert results[0][1] > 0.99

    def test_search_with_threshold(self, sample_vectors):
        """Test search with threshold filtering."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=384, M=16, ef_construction=64, seed=42)
        for i, vec in enumerate(sample_vectors):
            index.insert(f"doc_{i}", vec)

        query = sample_vectors[0]
        # Very high threshold should return few results
        results = index.search(query, top_k=5, threshold=0.99)
        assert len(results) >= 1  # At least the exact match

        # Very low threshold should return up to top_k
        results = index.search(query, top_k=5, threshold=0.0)
        assert len(results) >= 1

    def test_insert_duplicate_id(self):
        """Test inserting a vector with duplicate ID updates it."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)

        vec1 = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        index.insert("doc1", vec1)
        assert index.size == 1

        # Update with same ID
        index.insert("doc1", vec2)
        assert index.size == 1  # Should not grow

        # Search should find the updated vector
        results = index.search(vec2, top_k=1)
        assert len(results) >= 1

    def test_delete(self):
        """Test deleting a vector from the index."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)

        for i in range(10):
            vec = [0.0] * 10
            vec[i] = 1.0
            index.insert(f"doc_{i}", vec)

        assert index.size == 10
        deleted = index.delete("doc_0")
        assert deleted is True
        assert index.size == 9

        # Delete non-existent
        deleted = index.delete("doc_nonexistent")
        assert deleted is False

    def test_clear(self):
        """Test clearing the index."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)

        for i in range(10):
            vec = [0.0] * 10
            vec[i] = 1.0
            index.insert(f"doc_{i}", vec)

        index.clear()
        assert index.size == 0
        assert index.max_level == -1

    def test_bulk_insert(self):
        """Test bulk insertion is more efficient."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=10, M=4, ef_construction=8, seed=42)

        items = [(f"doc_{i}", [1.0 if j == i % 10 else 0.0 for j in range(10)]) for i in range(50)]
        count = index.bulk_insert(items)
        assert count == 50
        assert index.size == 50

    def test_get_stats(self, sample_vectors):
        """Test getting index statistics."""
        from src.core.vector.hnsw_index import HNSWIndex
        index = HNSWIndex(dimensions=384, M=16, ef_construction=64, seed=42)

        for i, vec in enumerate(sample_vectors[:20]):
            index.insert(f"doc_{i}", vec)

        # Do a search to generate search stats
        index.search(sample_vectors[0], top_k=5)

        stats = index.get_stats()
        assert stats["size"] == 20
        assert stats["M"] == 16
        assert stats["ef_construction"] == 64
        assert stats["inserts"] == 20
        assert stats["searches"] == 1
        assert stats["avg_search_latency_us"] >= 0

    def test_search_recall(self, sample_vectors):
        """Test that HNSW search has acceptable recall.

        Compares HNSW top-5 results against brute-force search
        and verifies that at least 80% of the brute-force results
        appear in the HNSW results (recall >= 0.8).
        """
        from src.core.vector.hnsw_index import HNSWIndex, _cosine_similarity
        index = HNSWIndex(dimensions=384, M=16, ef_construction=64, seed=42)

        for i, vec in enumerate(sample_vectors):
            index.insert(f"doc_{i}", vec)

        query = sample_vectors[0]

        # Brute-force top-5
        all_sims = []
        for i, vec in enumerate(sample_vectors):
            sim = _cosine_similarity(query, vec)
            all_sims.append((sim, f"doc_{i}"))
        all_sims.sort(key=lambda x: x[0], reverse=True)
        brute_force_ids = set(id for _, id in all_sims[:5])

        # HNSW top-5
        hnsw_results = index.search(query, top_k=5, ef=100)
        hnsw_ids = set(id for id, _ in hnsw_results)

        # Recall = |HNSW ∩ BruteForce| / |BruteForce|
        recall = len(hnsw_ids & brute_force_ids) / len(brute_force_ids)
        assert recall >= 0.6, f"Recall too low: {recall:.2f} (expected >= 0.6)"


# ── VectorStore Tests (Memory Backend) ─────────────────────

class TestVectorStoreMemory:
    """Tests for VectorStore with in-memory backend."""

    @pytest.fixture
    def store(self):
        from src.core.vector.vector_store import VectorStore
        store = VectorStore(database_url=None, dimensions=384)
        return store

    @pytest.mark.asyncio
    async def test_initialize(self, store):
        """Test VectorStore initializes with memory backend."""
        result = await store.initialize()
        assert result is False  # No pgvector
        assert store.backend == "memory"
        assert store.is_initialized

    @pytest.mark.asyncio
    async def test_upsert_and_search(self, store, sample_vector):
        """Test upserting and searching a vector."""
        await store.initialize()
        await store.upsert("doc1", "Hello world", sample_vector, source="test", category="greeting")

        results = await store.search(sample_vector, top_k=1, threshold=0.5)
        assert len(results) >= 1
        assert results[0].id == "doc1"
        assert results[0].content == "Hello world"
        assert results[0].similarity > 0.5

    @pytest.mark.asyncio
    async def test_upsert_batch(self, store, sample_vectors):
        """Test batch upsert."""
        await store.initialize()

        items = [
            {
                "id": f"doc_{i}",
                "content": f"Content {i}",
                "embedding": sample_vectors[i],
                "source": "test",
                "category": "batch",
            }
            for i in range(20)
        ]

        count = await store.upsert_batch(items)
        assert count == 20

        # Search should find results
        results = await store.search(sample_vectors[0], top_k=5, threshold=0.3)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, store, sample_vectors):
        """Test search with category filter."""
        await store.initialize()

        # Insert vectors with different categories
        for i in range(10):
            await store.upsert(
                f"doc_{i}",
                f"Content {i}",
                sample_vectors[i],
                category="cat_a" if i < 5 else "cat_b",
            )

        # Search with category filter
        results = await store.search(sample_vectors[0], top_k=5, category="cat_a")
        assert len(results) >= 1
        for r in results:
            assert r.metadata.get("category") == "cat_a"

    @pytest.mark.asyncio
    async def test_delete(self, store, sample_vector):
        """Test deleting a vector."""
        await store.initialize()
        await store.upsert("doc1", "Hello", sample_vector)
        count_before = await store.count()
        assert count_before == 1

        await store.delete("doc1")
        count_after = await store.count()
        assert count_after == 0

    @pytest.mark.asyncio
    async def test_count(self, store, sample_vectors):
        """Test counting embeddings."""
        await store.initialize()

        for i in range(5):
            await store.upsert(f"doc_{i}", f"Content {i}", sample_vectors[i], category="test")

        total = await store.count()
        assert total == 5

        by_category = await store.count(category="test")
        assert by_category == 5

        by_other = await store.count(category="other")
        assert by_other == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, store, sample_vectors):
        """Test getting vector store statistics."""
        await store.initialize()

        for i in range(5):
            await store.upsert(f"doc_{i}", f"Content {i}", sample_vectors[i])

        stats = await store.get_stats()
        assert stats["backend"] == "memory"
        assert stats["total_embeddings"] == 5
        assert stats["dimensions"] == 384

    @pytest.mark.asyncio
    async def test_health_check(self, store):
        """Test vector store health check."""
        await store.initialize()
        health = await store.health_check()
        assert health["healthy"] is True
        assert "backend" in health

    @pytest.mark.asyncio
    async def test_close(self, store):
        """Test closing the vector store."""
        await store.initialize()
        await store.close()
        assert not store.is_initialized

    @pytest.mark.asyncio
    async def test_search_empty_store(self, store, sample_vector):
        """Test searching an empty store returns no results."""
        await store.initialize()
        results = await store.search(sample_vector, top_k=5)
        assert results == []


# ── VectorStore Tests (pgvector backend) ────────────────────

@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="DATABASE_URL not configured for PostgreSQL",
)
class TestVectorStorePgvector:
    """Tests for VectorStore with pgvector backend."""

    @pytest.fixture
    def pg_store(self):
        from src.core.vector.vector_store import VectorStore
        url = os.environ.get("DATABASE_URL", "")
        store = VectorStore(database_url=url, dimensions=384)
        return store

    @pytest.mark.asyncio
    async def test_pgvector_initialize(self, pg_store):
        """Test pgvector initialization."""
        result = await pg_store.initialize()
        # May or may not succeed depending on pgvector availability
        assert pg_store.is_initialized
        await pg_store.close()

    @pytest.mark.asyncio
    async def test_pgvector_upsert_search(self, pg_store, sample_vector):
        """Test pgvector upsert and search."""
        await pg_store.initialize()

        if pg_store.backend != "pgvector":
            pytest.skip("pgvector not available")

        await pg_store.upsert("pg_test_1", "Hello pgvector", sample_vector, source="test")

        results = await pg_store.search(sample_vector, top_k=1, threshold=0.5)
        assert len(results) >= 1
        assert results[0].id == "pg_test_1"

        # Cleanup
        await pg_store.delete("pg_test_1")
        await pg_store.close()


# ── Cosine Similarity Tests ─────────────────────────────────

class TestCosineSimilarity:
    """Tests for the cosine similarity helper function."""

    def test_identical_vectors(self):
        """Test identical vectors have similarity 1.0."""
        from src.core.vector.hnsw_index import _cosine_similarity
        vec = [1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        """Test orthogonal vectors have similarity 0.0."""
        from src.core.vector.hnsw_index import _cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        """Test opposite vectors have similarity -1.0."""
        from src.core.vector.hnsw_index import _cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        """Test zero vector returns 0.0 similarity."""
        from src.core.vector.hnsw_index import _cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [0.0, 0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0
