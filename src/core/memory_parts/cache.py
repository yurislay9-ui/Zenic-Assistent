"""
ZENIC-AGENTS - SmartMemory Cache Mixin

Semantic cache and working memory methods for SmartMemory.
Phase 2: Fully tenant-aware — all queries scoped by tenant_id.

FASE 1.2 Performance Fix:
- Replaced all raw sqlite3.connect(DB_PATH) calls with FastPool.
- Read operations use smart_memory_pool.get() for thread-local cached connections.
- Write operations use smart_memory_pool.write() for thread-safe auto-commit.
- Connections are NOT closed — the pool manages their lifecycle.
- This eliminates SQLITE_BUSY errors from competing connection systems.
"""

import time
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List

from .types import (
    MemoryEntry, logger,
    MAX_WORKING_ENTRIES, MAX_COMPRESSED_TOKENS,
    IMPORTANCE_THRESHOLD, SEMANTIC_CACHE_THRESHOLD,
)
from .types import HAS_NUMPY
from .pool import smart_memory_pool, SMART_MEMORY_DB

if HAS_NUMPY:
    import numpy as np


class CacheMixin:
    """
    Mixin providing semantic cache and working memory methods for SmartMemory.
    All queries are scoped by both tenant_id and client_id.

    FASE 1.2: All database access now goes through smart_memory_pool
    instead of raw sqlite3.connect() calls.
    """

    # ================================================================
    #  1. SEMANTIC CACHE (tenant-aware)
    # ================================================================

    def check_cache(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Busca en el cache semántico: "Ya respondí algo similar antes?"
        
        Usa embeddings si SemanticEngine está disponible, si no usa hash exacto.
        Scoped by tenant_id and client_id.
        Returns cached response or None.

        FASE 1.2: Uses smart_memory_pool for all DB access.
        """
        # First: exact hash match (fastest) — scoped by tenant AND client
        # FASE 1.2: Use pool's write() since this includes an UPDATE (access_count)
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT response_summary, operation, goal, importance, access_count, id
                   FROM semantic_cache
                   WHERE query_hash=? AND tenant_id=? AND client_id=?""",
                (query_hash, self._tenant_id, self._client_id)
            ).fetchone()
            if row:
                # Update access count
                conn.execute("UPDATE semantic_cache SET access_count=access_count+1 WHERE id=?", (row[5],))  # nosemgrep: sqlalchemy-execute-raw-query
                return {
                    "response": row[0],
                    "operation": row[1],
                    "goal": row[2],
                    "importance": row[3],
                    "source": "cache_exact",
                }

        # Second: semantic similarity match (if SemanticEngine available)
        if self._semantic and self._semantic.is_loaded:
            query_emb = self._semantic.embed(query)
            if query_emb is not None:
                # FASE 1.2: Use pool.get() for read-only query (no write lock needed)
                conn = smart_memory_pool.get(SMART_MEMORY_DB)
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT id, query_text, response_summary, operation, goal, importance, embedding
                       FROM semantic_cache
                       WHERE tenant_id=? AND client_id=?
                       ORDER BY id DESC LIMIT 100""",
                    (self._tenant_id, self._client_id)
                ).fetchall()

                for row in rows:
                    cache_emb = self._deserialize_embedding(row[6])
                    if cache_emb is not None:
                        sim = self._semantic.similarity(query_emb, cache_emb)
                        if sim >= SEMANTIC_CACHE_THRESHOLD:
                            # FASE 1.2: Use pool's write() for UPDATE (access_count)
                            with smart_memory_pool.write(SMART_MEMORY_DB) as w_conn:
                                w_conn.execute("UPDATE semantic_cache SET access_count=access_count+1 WHERE id=?", (row[0],))  # nosemgrep: sqlalchemy-execute-raw-query
                            return {
                                "response": row[2],
                                "operation": row[3],
                                "goal": row[4],
                                "importance": row[5],
                                "similarity": sim,
                                "source": "cache_semantic",
                            }

        return None

    def save_to_cache(self, query: str, response: str, operation: str = "",
                       goal: str = "", importance: float = 0.5):
        """Guarda una entrada en el cache semántico (tenant-aware).

        FASE 1.2: Uses smart_memory_pool.write() for INSERT.
        """
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        
        # Compute embedding if possible
        emb_blob = None
        if self._semantic and self._semantic.is_loaded:
            emb = self._semantic.embed(query)
            if emb is not None:
                emb_blob = self._serialize_embedding(emb)

        # Truncate response for storage
        response_summary = response[:2000] if response else ""

        # FASE 1.2: Use pool's write() for INSERT (auto-commit, write-locked)
        with smart_memory_pool.write(SMART_MEMORY_DB) as conn:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO semantic_cache 
                   (query_hash, query_text, response_summary, operation, goal,
                    importance, embedding, created_at, session_id, client_id, tenant_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_hash, query[:500], response_summary, operation, goal,
                 importance, emb_blob, time.time(), self._session_id,
                 self._client_id, self._tenant_id)
            )
            # write() auto-commits on exit

        # If high importance, also save to long-term
        if importance >= IMPORTANCE_THRESHOLD:
            self.save_to_long_term(query, response_summary, operation, goal, importance)

    # ================================================================
    #  2. WORKING MEMORY (context for Qwen, tenant-aware)
    # ================================================================

    def add_working(self, query: str, response: str, operation: str = "", 
                     goal: str = "", importance: float = 0.5):
        """Añade entrada a la memoria de trabajo (contexto actual, tenant-aware)."""
        entry = MemoryEntry(
            query=query[:500],
            response=response[:1000],
            operation=operation,
            goal=goal,
            importance=importance,
            timestamp=time.time(),
            session_id=self._session_id,
            client_id=self._client_id,
            tenant_id=self._tenant_id,
        )
        with self._working_lock:
            self._working_memory.append(entry)

            # Evict lowest importance if over limit
            if len(self._working_memory) > MAX_WORKING_ENTRIES:
                min_entry = min(self._working_memory, key=lambda e: e.importance)
                self._working_memory.remove(min_entry)

    def get_working_context(self, max_tokens: int = MAX_COMPRESSED_TOKENS) -> str:
        """
        Obtiene contexto comprimido de la memoria de trabajo para Qwen.
        
        Formato: "Previous context: [summarized interactions]"
        Scoped by tenant_id and client_id.
        """
        with self._working_lock:
            if not self._working_memory:
                return ""

            # Build context from working memory, prioritizing important entries
            # Filter by tenant_id and client_id
            scoped_entries = [
                e for e in self._working_memory
                if e.tenant_id == self._tenant_id and e.client_id == self._client_id
            ]
            sorted_entries = sorted(scoped_entries, key=lambda e: (-e.importance, -e.timestamp))

        context_parts = []
        token_estimate = 0
        
        for entry in sorted_entries:
            part = f"[{entry.operation}/{entry.goal}] Q: {entry.query[:80]}"
            if entry.response:
                part += f" → A: {entry.response[:100]}"
            
            part_tokens = len(part.split())  # Rough estimate
            if token_estimate + part_tokens > max_tokens:
                break
            
            context_parts.append(part)
            token_estimate += part_tokens

        if not context_parts:
            return ""

        return "Previous context: " + " | ".join(context_parts)

    def get_recent_operations(self, n: int = 5) -> List[str]:
        """Obtiene las últimas N operaciones realizadas (tenant-scoped)."""
        with self._working_lock:
            return [
                e.operation for e in self._working_memory[-n:]
                if e.operation and e.tenant_id == self._tenant_id
            ]
