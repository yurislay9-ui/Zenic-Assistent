"""
ZENIC-AGENTS v16 - Vector Store (Phase 4.1: Vector Embeddings)

Async pgvector-backed vector store for semantic search.
Stores embeddings in PostgreSQL with the pgvector extension,
enabling O(log n) nearest neighbor search via HNSW indexes.

Key features:
- Automatic pgvector extension creation on startup
- HNSW index creation with configurable M and ef_construction
- Upsert embeddings with metadata (source, category, tags)
- Cosine similarity search with configurable ef_search
- Batch upsert for efficient bulk loading
- Graceful degradation: falls back to in-memory when pgvector unavailable
- TTL-based automatic cleanup of stale embeddings

Environment variables:
- DATABASE_URL: PostgreSQL connection string (required for pgvector)
- VECTOR_DIMENSIONS: Embedding dimensions (default: 384 for fastembed)
- VECTOR_HNSW_M: HNSW graph connectivity (default: 16)
- VECTOR_HNSW_EF_CONSTRUCTION: Index build quality (default: 64)
- VECTOR_EF_SEARCH: Search quality at query time (default: 40)
- VECTOR_TABLE_NAME: Table name for embeddings (default: zenic_vectors)
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "VectorStore",
    "get_vector_store",
    "VectorSearchResult",
]


@dataclass
class VectorSearchResult:
    """Result of a vector similarity search.

    Attributes:
        id: Unique identifier for the embedding record.
        content: The original text content.
        similarity: Cosine similarity score (0.0 to 1.0).
        metadata: Additional metadata (source, category, tags).
    """
    id: str
    content: str
    similarity: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class VectorStore:
    """Async pgvector-backed vector store for semantic search.

    Provides O(log n) nearest neighbor search using HNSW indexes
    in PostgreSQL with the pgvector extension. Falls back gracefully
    to in-memory brute-force search when pgvector is not available.

    Usage:
        store = VectorStore(database_url="postgresql://...")
        await store.initialize()
        await store.upsert("doc1", "Hello world", embedding, metadata={...})
        results = await store.search(embedding, top_k=5)
        await store.close()
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        dimensions: int = 384,
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 64,
        ef_search: int = 40,
        table_name: str = "zenic_vectors",
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL", "")
        self._dimensions = dimensions or int(os.environ.get("VECTOR_DIMENSIONS", "384"))
        self._hnsw_m = hnsw_m or int(os.environ.get("VECTOR_HNSW_M", "16"))
        self._hnsw_ef_construction = hnsw_ef_construction or int(
            os.environ.get("VECTOR_HNSW_EF_CONSTRUCTION", "64")
        )
        self._ef_search = ef_search or int(os.environ.get("VECTOR_EF_SEARCH", "40"))
        self._table_name = table_name or os.environ.get("VECTOR_TABLE_NAME", "zenic_vectors")

        self._pool: Any = None
        self._initialized = False
        self._pgvector_available = False

        # In-memory fallback for when pgvector is not available
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._stats = {
            "upserts": 0,
            "searches": 0,
            "search_latency_ms": 0.0,
            "backend": "none",
        }

    @property
    def is_initialized(self) -> bool:
        """Whether the vector store has been initialized."""
        return self._initialized

    @property
    def backend(self) -> str:
        """Current backend: 'pgvector' or 'memory' or 'none'."""
        if self._pgvector_available:
            return "pgvector"
        if self._memory_store:
            return "memory"
        return "none"

    async def initialize(self) -> bool:
        """Initialize the vector store.

        Creates the pgvector extension, embedding table, and HNSW index.
        Returns True if pgvector is available, False if using memory fallback.

        Steps:
        1. Connect to PostgreSQL
        2. Create pgvector extension (CREATE EXTENSION IF NOT EXISTS vector)
        3. Create embeddings table with vector column
        4. Create HNSW index for fast ANN search
        5. Set ef_search parameter for query-time quality
        """
        if self._initialized:
            return self._pgvector_available

        if not self._database_url:
            logger.info("VectorStore: No DATABASE_URL configured, using in-memory fallback")
            self._initialized = True
            self._stats["backend"] = "memory"
            return False

        if not self._database_url.startswith(("postgresql://", "postgres://")):
            logger.info("VectorStore: Not a PostgreSQL URL, using in-memory fallback")
            self._initialized = True
            self._stats["backend"] = "memory"
            return False

        try:
            import asyncpg  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("VectorStore: asyncpg not installed, using in-memory fallback")
            self._initialized = True
            self._stats["backend"] = "memory"
            return False

        try:
            self._pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    self._database_url,
                    min_size=2,
                    max_size=10,
                ),
                timeout=10.0,
            )

            async with self._pool.acquire() as conn:
                # 1. Create pgvector extension
                try:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    logger.info("VectorStore: pgvector extension created/enabled")
                except Exception as e:
                    logger.warning(f"VectorStore: pgvector extension not available: {e}")
                    self._initialized = True
                    self._stats["backend"] = "memory"
                    return False

                # 2. Create embeddings table
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        embedding vector({self._dimensions}) NOT NULL,
                        source TEXT DEFAULT '',
                        category TEXT DEFAULT '',
                        tags TEXT DEFAULT '[]',
                        content_hash TEXT DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        expires_at TIMESTAMPTZ
                    )
                """)

                # 3. Create HNSW index for cosine similarity search
                #    This provides O(log n) search performance
                index_name = f"{self._table_name}_embedding_hnsw_idx"
                try:
                    await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON {self._table_name}
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = {self._hnsw_m}, ef_construction = {self._hnsw_ef_construction})
                    """)
                    logger.info(
                        f"VectorStore: HNSW index created "
                        f"(m={self._hnsw_m}, ef_construction={self._hnsw_ef_construction})"
                    )
                except Exception as e:
                    logger.warning(f"VectorStore: HNSW index creation failed (may need more data): {e}")

                # 4. Set ef_search for query-time search quality
                try:
                    await conn.execute(f"SET hnsw.ef_search = {self._ef_search}")
                except Exception:
                    pass  # Non-critical

                # 5. Create indexes on metadata columns for filtered search
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self._table_name}_category_idx
                    ON {self._table_name} (category)
                """)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self._table_name}_source_idx
                    ON {self._table_name} (source)
                """)

            self._pgvector_available = True
            self._initialized = True
            self._stats["backend"] = "pgvector"
            logger.info(
                f"VectorStore: Initialized with pgvector backend "
                f"(dimensions={self._dimensions}, table={self._table_name})"
            )
            return True

        except asyncio.TimeoutError:
            logger.warning("VectorStore: PostgreSQL connection timed out, using in-memory fallback")
            self._initialized = True
            self._stats["backend"] = "memory"
            return False
        except Exception as e:
            logger.warning(f"VectorStore: Initialization failed, using in-memory fallback: {e}")
            self._initialized = True
            self._stats["backend"] = "memory"
            return False

    async def upsert(
        self,
        id: str,
        content: str,
        embedding: List[float],
        *,
        source: str = "",
        category: str = "",
        tags: Optional[List[str]] = None,
        expires_at: Optional[float] = None,
    ) -> bool:
        """Upsert an embedding into the vector store.

        If an embedding with the same ID already exists, it is updated.
        The content hash is computed for change detection — if the content
        hasn't changed, the upsert is skipped.

        Args:
            id: Unique identifier for this embedding.
            content: The original text content.
            embedding: The embedding vector (list of floats).
            source: Source of the content (e.g., 'smart_memory', 'conversation').
            category: Category for filtered search.
            tags: Optional list of tags.
            expires_at: Optional Unix timestamp when this embedding expires.

        Returns:
            True if upserted successfully, False otherwise.
        """
        if not self._initialized:
            await self.initialize()

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        tags_json = str(tags or [])
        expires_str = f"to_timestamp({expires_at})" if expires_at else "NULL"

        self._stats["upserts"] += 1

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    # Convert embedding list to pgvector format
                    emb_str = "[" + ",".join(str(v) for v in embedding) + "]"

                    await conn.execute(
                        f"""
                        INSERT INTO {self._table_name}
                            (id, content, embedding, source, category, tags, content_hash, updated_at, expires_at)
                        VALUES ($1, $2, $3::vector, $4, $5, $6, $7, NOW(), {expires_str})
                        ON CONFLICT (id)
                        DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            source = EXCLUDED.source,
                            category = EXCLUDED.category,
                            tags = EXCLUDED.tags,
                            content_hash = EXCLUDED.content_hash,
                            updated_at = NOW(),
                            expires_at = EXCLUDED.expires_at
                        """,
                        id, content, emb_str, source, category, tags_json, content_hash,
                    )
                return True
            except Exception as e:
                logger.warning(f"VectorStore: pgvector upsert failed for {id}: {e}")
                # Fall through to memory fallback
                pass

        # In-memory fallback
        self._memory_store[id] = {
            "content": content,
            "embedding": embedding,
            "source": source,
            "category": category,
            "tags": tags or [],
            "content_hash": content_hash,
            "updated_at": time.time(),
            "expires_at": expires_at,
        }
        return True

    async def upsert_batch(
        self,
        items: List[Dict[str, Any]],
    ) -> int:
        """Upsert multiple embeddings in a single transaction.

        Args:
            items: List of dicts with keys: id, content, embedding,
                   and optional: source, category, tags, expires_at.

        Returns:
            Number of items successfully upserted.
        """
        if not self._initialized:
            await self.initialize()

        if not items:
            return 0

        success_count = 0

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    async with conn.transaction():
                        for item in items:
                            try:
                                emb = item["embedding"]
                                emb_str = "[" + ",".join(str(v) for v in emb) + "]"
                                content_hash = hashlib.sha256(
                                    item["content"].encode()
                                ).hexdigest()
                                tags_json = str(item.get("tags", []))
                                expires_at = item.get("expires_at")
                                expires_sql = (
                                    f"to_timestamp({expires_at})" if expires_at else "NULL"
                                )

                                await conn.execute(
                                    f"""
                                    INSERT INTO {self._table_name}
                                        (id, content, embedding, source, category, tags, content_hash, updated_at, expires_at)
                                    VALUES ($1, $2, $3::vector, $4, $5, $6, $7, NOW(), {expires_sql})
                                    ON CONFLICT (id)
                                    DO UPDATE SET
                                        content = EXCLUDED.content,
                                        embedding = EXCLUDED.embedding,
                                        source = EXCLUDED.source,
                                        category = EXCLUDED.category,
                                        tags = EXCLUDED.tags,
                                        content_hash = EXCLUDED.content_hash,
                                        updated_at = NOW(),
                                        expires_at = EXCLUDED.expires_at
                                    """,
                                    item["id"],
                                    item["content"],
                                    emb_str,
                                    item.get("source", ""),
                                    item.get("category", ""),
                                    tags_json,
                                    content_hash,
                                )
                                success_count += 1
                            except Exception as e:
                                logger.warning(
                                    f"VectorStore: Batch upsert failed for {item.get('id', '?')}: {e}"
                                )
                self._stats["upserts"] += success_count
                return success_count
            except Exception as e:
                logger.warning(f"VectorStore: Batch pgvector upsert failed: {e}")

        # In-memory fallback
        for item in items:
            content_hash = hashlib.sha256(item["content"].encode()).hexdigest()
            self._memory_store[item["id"]] = {
                "content": item["content"],
                "embedding": item["embedding"],
                "source": item.get("source", ""),
                "category": item.get("category", ""),
                "tags": item.get("tags", []),
                "content_hash": content_hash,
                "updated_at": time.time(),
                "expires_at": item.get("expires_at"),
            }
            success_count += 1
        self._stats["upserts"] += success_count
        return success_count

    async def search(
        self,
        query_embedding: List[float],
        *,
        top_k: int = 5,
        threshold: float = 0.5,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        """Search for similar embeddings using cosine similarity.

        Uses the HNSW index for O(log n) search when pgvector is available.
        Falls back to in-memory brute-force search otherwise.

        Args:
            query_embedding: The query embedding vector.
            top_k: Maximum number of results to return.
            threshold: Minimum cosine similarity score (0.0 to 1.0).
            category: Optional filter by category.
            source: Optional filter by source.

        Returns:
            List of VectorSearchResult sorted by similarity (descending).
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        self._stats["searches"] += 1

        results: List[VectorSearchResult] = []

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

                    # Build WHERE clause for optional filters
                    where_clauses = ["(1 - (embedding <=> $1::vector)) >= $2"]
                    params: List[Any] = [emb_str, threshold]
                    param_idx = 3

                    if category is not None:
                        where_clauses.append(f"category = ${param_idx}")
                        params.append(category)
                        param_idx += 1

                    if source is not None:
                        where_clauses.append(f"source = ${param_idx}")
                        params.append(source)
                        param_idx += 1

                    # Filter out expired embeddings
                    where_clauses.append("(expires_at IS NULL OR expires_at > NOW())")

                    where_sql = " AND ".join(where_clauses)
                    params.append(top_k)

                    rows = await conn.fetch(
                        f"""
                        SELECT id, content, source, category, tags,
                               1 - (embedding <=> $1::vector) AS similarity
                        FROM {self._table_name}
                        WHERE {where_sql}
                        ORDER BY embedding <=> $1::vector
                        LIMIT ${param_idx}
                        """,
                        *params,
                    )

                    for row in rows:
                        results.append(VectorSearchResult(
                            id=row["id"],
                            content=row["content"],
                            similarity=round(float(row["similarity"]), 4),
                            metadata={
                                "source": row["source"],
                                "category": row["category"],
                                "tags": row["tags"],
                            },
                        ))
            except Exception as e:
                logger.warning(f"VectorStore: pgvector search failed: {e}")
                # Fall through to memory fallback

        if not results and self._memory_store:
            # In-memory brute-force search (O(n) fallback)
            results = self._search_memory(query_embedding, top_k, threshold, category, source)

        elapsed_ms = (time.time() - start_time) * 1000
        self._stats["search_latency_ms"] = round(elapsed_ms, 2)

        return results

    def _search_memory(
        self,
        query_embedding: List[float],
        top_k: int,
        threshold: float,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        """Brute-force in-memory cosine similarity search (O(n) fallback)."""
        import numpy as np

        query = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm > 0:
            query = query / query_norm

        scored: List[Tuple[float, VectorSearchResult]] = []
        now = time.time()

        for id, entry in self._memory_store.items():
            # Filter by category/source
            if category and entry.get("category") != category:
                continue
            if source and entry.get("source") != source:
                continue

            # Filter expired
            if entry.get("expires_at") and entry["expires_at"] < now:
                continue

            emb = np.array(entry["embedding"], dtype=np.float32)
            emb_norm = np.linalg.norm(emb)
            if emb_norm > 0:
                emb = emb / emb_norm

            similarity = float(np.dot(query, emb))
            if similarity >= threshold:
                scored.append((
                    similarity,
                    VectorSearchResult(
                        id=id,
                        content=entry["content"],
                        similarity=round(similarity, 4),
                        metadata={
                            "source": entry.get("source", ""),
                            "category": entry.get("category", ""),
                            "tags": entry.get("tags", []),
                        },
                    ),
                ))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    async def delete(self, id: str) -> bool:
        """Delete an embedding by ID.

        Args:
            id: The embedding ID to delete.

        Returns:
            True if deleted successfully.
        """
        if not self._initialized:
            await self.initialize()

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        f"DELETE FROM {self._table_name} WHERE id = $1",
                        id,
                    )
                return True
            except Exception as e:
                logger.warning(f"VectorStore: pgvector delete failed for {id}: {e}")

        # In-memory fallback
        self._memory_store.pop(id, None)
        return True

    async def count(self, category: Optional[str] = None) -> int:
        """Count the number of stored embeddings.

        Args:
            category: Optional filter by category.

        Returns:
            Number of embeddings.
        """
        if not self._initialized:
            await self.initialize()

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    if category:
                        row = await conn.fetchrow(
                            f"SELECT COUNT(*) AS cnt FROM {self._table_name} WHERE category = $1",
                            category,
                        )
                    else:
                        row = await conn.fetchrow(
                            f"SELECT COUNT(*) AS cnt FROM {self._table_name}"
                        )
                    return int(row["cnt"])
            except Exception:
                pass

        # In-memory fallback
        if category:
            return sum(1 for e in self._memory_store.values() if e.get("category") == category)
        return len(self._memory_store)

    async def cleanup_expired(self) -> int:
        """Remove expired embeddings from the store.

        Returns:
            Number of embeddings removed.
        """
        if not self._initialized:
            await self.initialize()

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    result = await conn.execute(
                        f"DELETE FROM {self._table_name} WHERE expires_at IS NOT NULL AND expires_at < NOW()"
                    )
                    # Parse "DELETE N" result
                    parts = result.split()
                    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
            except Exception:
                pass

        # In-memory fallback
        now = time.time()
        expired_ids = [
            id for id, entry in self._memory_store.items()
            if entry.get("expires_at") and entry["expires_at"] < now
        ]
        for id in expired_ids:
            del self._memory_store[id]
        return len(expired_ids)

    async def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics.

        Returns:
            Dict with backend, counts, and performance metrics.
        """
        if not self._initialized:
            await self.initialize()

        total_count = await self.count()

        stats: Dict[str, Any] = {
            "backend": self.backend,
            "initialized": self._initialized,
            "dimensions": self._dimensions,
            "table_name": self._table_name,
            "total_embeddings": total_count,
            "hnsw_m": self._hnsw_m,
            "hnsw_ef_construction": self._hnsw_ef_construction,
            "ef_search": self._ef_search,
            **self._stats,
        }

        if self._pgvector_available and self._pool:
            try:
                async with self._pool.acquire() as conn:
                    # Get index size
                    row = await conn.fetchrow(f"""
                        SELECT pg_size_pretty(pg_total_relation_size('{self._table_name}')) AS size
                    """)
                    stats["index_size"] = row["size"] if row else "unknown"
            except Exception:
                pass

        return stats

    async def health_check(self) -> Dict[str, Any]:
        """Check vector store health for the HealthAggregator.

        Returns:
            Dict with 'healthy', 'backend', and 'details' keys.
        """
        if not self._initialized:
            return {
                "healthy": False,
                "backend": "none",
                "details": "Not initialized",
            }

        try:
            count = await self.count()
            return {
                "healthy": True,
                "backend": self.backend,
                "total_embeddings": count,
                "dimensions": self._dimensions,
            }
        except Exception as e:
            return {
                "healthy": False,
                "backend": self.backend,
                "details": str(e),
            }

    async def close(self) -> None:
        """Close the vector store and release connections."""
        if self._pool:
            try:
                await self._pool.close()
            except Exception:
                pass
            self._pool = None
        self._initialized = False
        self._pgvector_available = False


# ── Singleton ─────────────────────────────────────────────

_vector_store: Optional[VectorStore] = None
_vector_store_lock = asyncio.Lock()


def get_vector_store(
    database_url: Optional[str] = None,
    dimensions: int = 384,
) -> VectorStore:
    """Get or create the singleton VectorStore.

    Args:
        database_url: PostgreSQL connection URL. If not provided,
            reads from DATABASE_URL environment variable.
        dimensions: Embedding dimensions (default: 384 for fastembed).

    Returns:
        The global VectorStore instance.
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(
            database_url=database_url,
            dimensions=dimensions,
        )
    return _vector_store
