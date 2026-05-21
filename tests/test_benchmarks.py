"""
ZENIC-AGENTS v16 - Python Benchmark Suite (Phase 4.3)

Comprehensive performance benchmarks for all Phase 1-4 components.
Designed to run in CI with pytest-benchmark and produce JSON output
for regression detection.

Benchmark groups:
- BenchmarkFastPool: SQLite connection pool operations
- BenchmarkVectorStore: pgvector upsert/search performance
- BenchmarkHNSW: In-memory HNSW index performance
- BenchmarkRedis: Redis cache/session/rate-limiter performance
- BenchmarkCircuitBreaker: Circuit breaker state transitions
- BenchmarkHealthAggregator: Health check aggregation latency

Usage:
    pytest tests/test_benchmarks.py --benchmark-only -v
    pytest tests/test_benchmarks.py::BenchmarkHNSW --benchmark-only -v
"""

import asyncio
import os
import random
import time
from typing import List

import pytest

# ── Check optional dependencies ──────────────────────────────

HAS_NUMPY = False
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    pass

HAS_ASYNCPG = False
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    pass

HAS_REDIS = False
try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    pass


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def sample_embeddings():
    """Generate random sample embeddings for benchmarking."""
    if not HAS_NUMPY:
        pytest.skip("numpy not installed")
    rng = random.Random(42)
    embeddings = []
    for i in range(1000):
        vec = [rng.gauss(0, 1) for _ in range(384)]
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        embeddings.append(vec)
    return embeddings


@pytest.fixture
def hnsw_index():
    """Create a fresh HNSW index for benchmarking."""
    from src.core.vector.hnsw_index import HNSWIndex
    return HNSWIndex(dimensions=384, M=16, ef_construction=64, seed=42)


@pytest.fixture
def populated_hnsw(hnsw_index, sample_embeddings):
    """Create an HNSW index populated with 1000 vectors."""
    for i, emb in enumerate(sample_embeddings):
        hnsw_index.insert(f"doc_{i}", emb)
    return hnsw_index


# ── FastPool Benchmarks ─────────────────────────────────────

@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class BenchmarkFastPool:
    """Benchmarks for the unified SQLite FastPool (Phase 1)."""

    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "bench_test.db")

    def test_fast_pool_write(self, benchmark, db_path):
        """Benchmark single write operation through FastPool."""
        try:
            from src.core.memory_parts.pool import FastPool
        except ImportError:
            pytest.skip("FastPool not available")

        pool = FastPool(db_path)
        pool.initialize()

        def write_op():
            conn = pool.get_connection()
            try:
                conn.execute(
                    "INSERT INTO memory (key, value, timestamp) VALUES (?, ?, ?)",
                    ("bench_key", "bench_value", time.time()),
                )
                conn.commit()
            finally:
                pool.return_connection(conn)

        benchmark(write_op)
        pool.close()

    def test_fast_pool_read(self, benchmark, db_path):
        """Benchmark single read operation through FastPool."""
        try:
            from src.core.memory_parts.pool import FastPool
        except ImportError:
            pytest.skip("FastPool not available")

        pool = FastPool(db_path)
        pool.initialize()

        # Pre-populate
        conn = pool.get_connection()
        for i in range(100):
            conn.execute(
                "INSERT INTO memory (key, value, timestamp) VALUES (?, ?, ?)",
                (f"key_{i}", f"value_{i}", time.time()),
            )
        conn.commit()
        pool.return_connection(conn)

        def read_op():
            conn = pool.get_connection()
            try:
                cursor = conn.execute("SELECT value FROM memory WHERE key = ?", ("key_50",))
                cursor.fetchone()
            finally:
                pool.return_connection(conn)

        benchmark(read_op)
        pool.close()


# ── HNSW Index Benchmarks ───────────────────────────────────

class BenchmarkHNSW:
    """Benchmarks for the in-memory HNSW index (Phase 4.2)."""

    def test_hnsw_insert_single(self, benchmark, hnsw_index, sample_embeddings):
        """Benchmark inserting a single vector into HNSW."""
        idx = 0

        def insert_one():
            nonlocal idx
            hnsw_index.insert(f"bench_{idx}", sample_embeddings[idx % len(sample_embeddings)])
            idx += 1

        benchmark(insert_one)

    def test_hnsw_insert_batch_100(self, benchmark, hnsw_index, sample_embeddings):
        """Benchmark batch insertion of 100 vectors."""

        def insert_batch():
            items = [(f"bench_{i}", sample_embeddings[i]) for i in range(100)]
            hnsw_index.bulk_insert(items)
            hnsw_index.clear()

        benchmark(insert_batch)

    def test_hnsw_search_top5(self, benchmark, populated_hnsw, sample_embeddings):
        """Benchmark searching for top-5 similar vectors."""
        query = sample_embeddings[0]

        def search_top5():
            populated_hnsw.search(query, top_k=5, ef=40)

        benchmark(search_top5)

    def test_hnsw_search_top5_with_threshold(self, benchmark, populated_hnsw, sample_embeddings):
        """Benchmark searching for top-5 with threshold filter."""
        query = sample_embeddings[0]

        def search_filtered():
            populated_hnsw.search(query, top_k=5, ef=40, threshold=0.5)

        benchmark(search_filtered)

    def test_hnsw_search_top50(self, benchmark, populated_hnsw, sample_embeddings):
        """Benchmark searching for top-50 similar vectors (higher ef)."""
        query = sample_embeddings[0]

        def search_top50():
            populated_hnsw.search(query, top_k=50, ef=100)

        benchmark(search_top50)

    def test_hnsw_delete(self, benchmark, populated_hnsw):
        """Benchmark deleting a vector from HNSW."""

        def delete_one():
            populated_hnsw.delete("doc_0")

        benchmark(delete_one)

    def test_hnsw_get_stats(self, benchmark, populated_hnsw):
        """Benchmark getting index statistics."""

        def get_stats():
            populated_hnsw.get_stats()

        benchmark(get_stats)


# ── VectorStore Benchmarks ──────────────────────────────────

class BenchmarkVectorStore:
    """Benchmarks for the pgvector-backed VectorStore (Phase 4.1)."""

    def test_vector_store_memory_upsert(self, benchmark):
        """Benchmark in-memory VectorStore upsert."""
        from src.core.vector.vector_store import VectorStore

        store = VectorStore(database_url=None, dimensions=384)
        # Force memory backend
        store._initialized = True
        idx = 0

        def upsert_one():
            nonlocal idx
            emb = [random.gauss(0, 1) for _ in range(384)]
            asyncio.get_event_loop().run_until_complete(
                store.upsert(f"bench_{idx}", f"Content {idx}", emb)
            )
            idx += 1

        benchmark(upsert_one)

    def test_vector_store_memory_search(self, benchmark):
        """Benchmark in-memory VectorStore search."""
        from src.core.vector.vector_store import VectorStore

        store = VectorStore(database_url=None, dimensions=384)
        store._initialized = True

        # Populate
        async def populate():
            for i in range(100):
                emb = [random.gauss(0, 1) for _ in range(384)]
                await store.upsert(f"doc_{i}", f"Content {i}", emb)
        asyncio.get_event_loop().run_until_complete(populate())

        query = [random.gauss(0, 1) for _ in range(384)]

        def search_top5():
            asyncio.get_event_loop().run_until_complete(
                store.search(query, top_k=5, threshold=0.3)
            )

        benchmark(search_top5)


# ── Redis Benchmarks ────────────────────────────────────────

@pytest.mark.skipif(not HAS_REDIS, reason="redis not installed")
class BenchmarkRedis:
    """Benchmarks for Redis operations (Phase 2-3)."""

    @pytest.fixture
    def redis_url(self):
        return os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_redis_ping(self, benchmark, redis_url):
        """Benchmark Redis PING latency."""
        client = aioredis.from_url(redis_url)

        async def ping():
            await client.ping()

        await benchmark(ping)
        await client.close()

    @pytest.mark.asyncio
    async def test_redis_set_get(self, benchmark, redis_url):
        """Benchmark Redis SET/GET operations."""
        client = aioredis.from_url(redis_url)
        idx = 0

        async def set_get():
            nonlocal idx
            key = f"bench:{idx}"
            await client.set(key, f"value_{idx}", px=60000)
            await client.get(key)
            idx += 1

        await benchmark(set_get)
        await client.close()


# ── Circuit Breaker Benchmarks ──────────────────────────────

class BenchmarkCircuitBreaker:
    """Benchmarks for circuit breaker state transitions (Phase 3.2)."""

    def test_cb_record_success(self, benchmark):
        """Benchmark recording circuit breaker success."""
        try:
            from src.core.agents.resilience.circuit_breaker import AgentCircuitBreaker
        except ImportError:
            pytest.skip("CircuitBreaker not available")

        cb = AgentCircuitBreaker("bench-agent")

        def record_success():
            cb.record_success()

        benchmark(record_success)

    def test_cb_record_failure(self, benchmark):
        """Benchmark recording circuit breaker failure."""
        try:
            from src.core.agents.resilience.circuit_breaker import AgentCircuitBreaker
        except ImportError:
            pytest.skip("CircuitBreaker not available")

        cb = AgentCircuitBreaker("bench-agent")

        def record_failure():
            cb.record_failure(Exception("test"))

        benchmark(record_failure)

    def test_cb_check_state(self, benchmark):
        """Benchmark checking circuit breaker state."""
        try:
            from src.core.agents.resilience.circuit_breaker import AgentCircuitBreaker
        except ImportError:
            pytest.skip("CircuitBreaker not available")

        cb = AgentCircuitBreaker("bench-agent")

        def check_state():
            cb.can_execute()

        benchmark(check_state)


# ── Health Aggregator Benchmarks ────────────────────────────

class BenchmarkHealthAggregator:
    """Benchmarks for health check aggregation (Phase 3.4)."""

    def test_health_check_disk(self, benchmark):
        """Benchmark disk space health check."""
        from src.core.observability.health import check_disk_space

        def disk_check():
            asyncio.get_event_loop().run_until_complete(check_disk_space())

        benchmark(disk_check)

    def test_health_aggregator_readiness(self, benchmark):
        """Benchmark readiness check aggregation."""
        from src.core.observability.health import HealthAggregator

        agg = HealthAggregator(check_timeout=2.0)

        def readiness_check():
            asyncio.get_event_loop().run_until_complete(agg.check_readiness())

        benchmark(readiness_check)
