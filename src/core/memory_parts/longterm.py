"""
ZENIC-AGENTS - SmartMemory Long-term Memory Mixin

Long-term memory, similarity search, importance scoring,
embedding serialization, and stats methods for SmartMemory.
Phase 2: Fully tenant-aware — all queries scoped by tenant_id.
"""

import time
import json
import sqlite3
import logging
from typing import Optional, Dict, Any, List

from .types import (
    DB_PATH, logger,
    MAX_LONG_TERM_ENTRIES, IMPORTANCE_THRESHOLD,
)
from .types import HAS_NUMPY
if HAS_NUMPY:
    import numpy as np


class LongTermMixin:
    """
    Mixin providing long-term memory, similarity search, importance scoring,
    embedding serialization, and stats methods for SmartMemory.
    All queries are scoped by tenant_id.
    """

    # ================================================================
    #  3. LONG-TERM MEMORY (learning, tenant-aware)
    # ================================================================

    def save_to_long_term(self, query: str, solution: str, operation: str = "",
                           goal: str = "", importance: float = 0.5, 
                           success: bool = True, tags: Optional[List[str]] = None):
        """Guarda una solución exitosa en la memoria a largo plazo (tenant-aware)."""
        tags = tags or []
        emb_blob = None
        if self._semantic and self._semantic.is_loaded:
            emb = self._semantic.embed(query)
            if emb is not None:
                emb_blob = self._serialize_embedding(emb)

        tags_json = json.dumps(tags)

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO long_term_memory 
                   (query_text, solution_summary, operation, goal, importance,
                    success, embedding, created_at, tags, client_id, tenant_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query[:500], solution[:2000], operation, goal, importance,
                 success, emb_blob, time.time(), tags_json,
                 self._client_id, self._tenant_id)
            )

        # Evict if over limit
        self._evict_long_term()

    def find_similar_solutions(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Busca soluciones previas semánticamente similares (tenant-scoped).
        "La última vez que hicimos algo parecido, funcionó esto."
        """
        if not self._semantic or not self._semantic.is_loaded:
            return []

        query_emb = self._semantic.embed(query)
        if query_emb is None:
            return []

        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT id, query_text, solution_summary, operation, goal,
                          importance, success, embedding, tags
                   FROM long_term_memory
                   WHERE success=1 AND tenant_id=?
                   ORDER BY importance DESC LIMIT 100""",
                (self._tenant_id,)
            ).fetchall()

        results = []
        for row in rows:
            cache_emb = self._deserialize_embedding(row[7])
            if cache_emb is not None:
                sim = self._semantic.similarity(query_emb, cache_emb)
                if sim >= 0.5:
                    results.append({
                        "query": row[1],
                        "solution": row[2],
                        "operation": row[3],
                        "goal": row[4],
                        "importance": row[5],
                        "similarity": sim,
                        "tags": json.loads(row[8] or "[]"),
                    })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def _evict_long_term(self):
        """Evict least important entries if over limit (tenant-scoped)."""
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM long_term_memory WHERE tenant_id=?",
                (self._tenant_id,)
            ).fetchone()[0]
            if count > MAX_LONG_TERM_ENTRIES:
                # Delete lowest importance entries for this tenant
                conn.execute(
                    """DELETE FROM long_term_memory
                       WHERE id IN (
                           SELECT id FROM long_term_memory
                           WHERE tenant_id=?
                           ORDER BY importance ASC, access_count ASC
                           LIMIT ?
                       )""",
                    (self._tenant_id, count - MAX_LONG_TERM_ENTRIES + 50,)  # Delete extra 50 to avoid frequent eviction
                )

    # ================================================================
    #  UTILITY: Importance Scoring
    # ================================================================

    @staticmethod
    def compute_importance(query: str, operation: str, goal: str, 
                            success: bool, response_length: int) -> float:
        """
        Calcula la importancia de una interacción.
        
        Factores:
        - Operaciones críticas (DELETE, DEBUG) → más importantes
        - Goals de seguridad → más importantes
        - Interacciones exitosas → más importantes
        - Respuestas largas → posiblemente más complejas → más importantes
        """
        score = 0.5  # Base

        # Operation importance
        op_weights = {
            "DELETE": 0.2, "DEBUG": 0.15, "REFACTOR": 0.1,
            "CREATE": 0.05, "OPTIMIZE": 0.1, "ANALYZE": 0.05,
            "SEARCH": -0.1, "EXPLAIN": 0.0,
        }
        score += op_weights.get(operation, 0.0)

        # Goal importance
        goal_weights = {
            "SECURITY_HARDEN": 0.2, "BUG_FIX": 0.15,
            "PERFORMANCE": 0.1, "FEATURE_ADD": 0.05,
            "COMPLEXITY_REDUCTION": 0.05, "MODERN_PATTERN": 0.0,
            "READABILITY": 0.0,
        }
        score += goal_weights.get(goal, 0.0)

        # Success bonus
        if success:
            score += 0.1

        # Response length (longer = more complex, probably more important)
        if response_length > 500:
            score += 0.05
        if response_length > 1000:
            score += 0.05

        return max(0.0, min(1.0, score))

    # ================================================================
    #  UTILITY: Embedding Serialization
    # ================================================================

    @staticmethod
    def _serialize_embedding(emb) -> bytes:
        """Serialize embedding to bytes for SQLite storage."""
        if not HAS_NUMPY:
            return b''
        return emb.astype(np.float32).tobytes()

    @staticmethod
    def _deserialize_embedding(data: bytes):
        """Deserialize embedding from SQLite bytes."""
        if not HAS_NUMPY or data is None or len(data) == 0:
            return None
        try:
            emb = np.frombuffer(data, dtype=np.float32)
            # Normalize
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb
        except Exception:
            return None

    # ================================================================
    #  STATS & DEBUG
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas de uso de la memoria (tenant-scoped)."""
        with sqlite3.connect(DB_PATH) as conn:
            cache_count = conn.execute(
                "SELECT COUNT(*) FROM semantic_cache WHERE tenant_id=?",
                (self._tenant_id,)
            ).fetchone()[0]
            ltm_count = conn.execute(
                "SELECT COUNT(*) FROM long_term_memory WHERE tenant_id=?",
                (self._tenant_id,)
            ).fetchone()[0]

        return {
            "session_id": self._session_id,
            "client_id": self._client_id,
            "tenant_id": self._tenant_id,
            "working_memory_size": len(self._working_memory) if hasattr(self, '_working_lock') and self._working_lock else 0,
            "semantic_cache_size": cache_count,
            "long_term_memory_size": ltm_count,
            "semantic_engine_available": self._semantic is not None and self._semantic.is_loaded,
        }
