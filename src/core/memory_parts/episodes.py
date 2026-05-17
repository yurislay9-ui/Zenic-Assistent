"""
ZENIC-AGENTS - SmartMemory Episodes Mixin

Episodic memory, procedural memory (learned patterns),
project memory, and enhanced stats methods for SmartMemory.
Phase 2: Fully tenant-aware — all queries scoped by tenant_id.
"""

import time
import json
import sqlite3
import logging
from typing import Optional, Dict, Any, List

from .types import (
    DB_PATH, logger,
    MAX_EPISODIC_ENTRIES, MAX_PROCEDURAL_ENTRIES, MAX_PROJECT_ENTRIES,
)


class EpisodesMixin:
    """
    Mixin providing episodic memory, procedural memory (learned patterns),
    project memory, and enhanced stats methods for SmartMemory.
    All queries are scoped by tenant_id.
    """

    # ================================================================
    #  4. EPISODIC MEMORY (event history, tenant-aware)
    # ================================================================

    def save_episode(self, event_type: str, description: str, context: str = "",
                     outcome: str = "", importance: float = 0.5, tags: Optional[List[str]] = None):
        """Guarda un episodio en la memoria episodica (tenant-aware)."""
        tags = tags or []
        emb_blob = None
        if self._semantic and self._semantic.is_loaded:
            emb = self._semantic.embed(f"{event_type}: {description}")
            if emb is not None:
                emb_blob = self._serialize_embedding(emb)
        tags_json = json.dumps(tags)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO episodic_memory
                   (event_type, description, context, outcome, importance,
                    embedding, created_at, tags, client_id, tenant_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_type, description[:1000], context[:500], outcome[:200],
                 importance, emb_blob, time.time(), tags_json,
                 self._client_id, self._tenant_id)
            )
        self._evict_table("episodic_memory", MAX_EPISODIC_ENTRIES)

    def find_episodes(self, event_type: str = "", query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Busca episodios por tipo o similitud semantica (tenant-scoped)."""
        results = []
        if event_type:
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT id, event_type, description, context, outcome,
                              importance, created_at, tags
                       FROM episodic_memory
                       WHERE event_type=? AND tenant_id=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (event_type, self._tenant_id, limit)
                ).fetchall()
            results = [{"id": r[0], "event_type": r[1], "description": r[2], "context": r[3], "outcome": r[4], "importance": r[5], "created_at": r[6], "tags": json.loads(r[7] or "[]")} for r in rows]
        elif query and self._semantic and self._semantic.is_loaded:
            query_emb = self._semantic.embed(query)
            if query_emb is not None:
                with sqlite3.connect(DB_PATH) as conn:
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """SELECT id, event_type, description, context, outcome,
                                  importance, embedding, created_at, tags
                           FROM episodic_memory
                           WHERE tenant_id=?
                           ORDER BY created_at DESC LIMIT 200""",
                        (self._tenant_id,)).fetchall()
                for r in rows:
                    cache_emb = self._deserialize_embedding(r[6])
                    if cache_emb is not None:
                        sim = self._semantic.similarity(query_emb, cache_emb)
                        if sim >= 0.5:
                            results.append({"id": r[0], "event_type": r[1], "description": r[2], "context": r[3], "outcome": r[4], "importance": r[5], "similarity": sim, "created_at": r[7], "tags": json.loads(r[8] or "[]")})
                results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
                results = results[:limit]
        return results

    # ================================================================
    #  5. PROCEDURAL MEMORY (learned patterns, tenant-aware)
    # ================================================================

    def learn_pattern(self, pattern_name: str, pattern_type: str, description: str,
                       steps: Optional[List[str]] = None, success: bool = True):
        """Aprende un patron procedural. Trackea tasa de exito (tenant-aware)."""
        steps = steps or []
        emb_blob = None
        if self._semantic and self._semantic.is_loaded:
            emb = self._semantic.embed(description)
            if emb is not None:
                emb_blob = self._serialize_embedding(emb)
        steps_json = json.dumps(steps)
        with sqlite3.connect(DB_PATH) as conn:
            existing = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT id, success_count, fail_count FROM procedural_memory WHERE pattern_name=? AND client_id=? AND tenant_id=?",
                (pattern_name, self._client_id, self._tenant_id)
            ).fetchone()
            if existing:
                sc, fc = existing[1], existing[2]
                if success: sc += 1
                else: fc += 1
                rate = sc / max(sc + fc, 1)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "UPDATE procedural_memory SET success_count=?, fail_count=?, success_rate=?, last_used=?, steps=? WHERE id=?",
                    (sc, fc, rate, time.time(), steps_json, existing[0])
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO procedural_memory
                       (pattern_name, pattern_type, description, success_count,
                        fail_count, success_rate, steps, embedding, created_at,
                        last_used, client_id, tenant_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pattern_name, pattern_type, description, 1 if success else 0,
                     0 if success else 1, 1.0 if success else 0.0, steps_json,
                     emb_blob, time.time(), time.time(),
                     self._client_id, self._tenant_id)
                )

    def find_patterns(self, pattern_type: str = "", query: str = "", min_success_rate: float = 0.5, limit: int = 5) -> List[Dict[str, Any]]:
        """Busca patrones aprendidos relevantes (tenant-scoped)."""
        results = []
        with sqlite3.connect(DB_PATH) as conn:
            if pattern_type:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT pattern_name, pattern_type, description, success_count,
                              fail_count, success_rate, steps, created_at, last_used
                       FROM procedural_memory
                       WHERE pattern_type=? AND success_rate >= ? AND tenant_id=?
                       ORDER BY success_rate DESC, success_count DESC LIMIT ?""",
                    (pattern_type, min_success_rate, self._tenant_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT pattern_name, pattern_type, description, success_count,
                              fail_count, success_rate, steps, created_at, last_used
                       FROM procedural_memory
                       WHERE success_rate >= ? AND tenant_id=?
                       ORDER BY success_rate DESC, success_count DESC LIMIT ?""",
                    (min_success_rate, self._tenant_id, limit)
                ).fetchall()
        for r in rows:
            results.append({"pattern_name": r[0], "pattern_type": r[1], "description": r[2], "success_count": r[3], "fail_count": r[4], "success_rate": r[5], "steps": json.loads(r[6] or "[]"), "created_at": r[7], "last_used": r[8]})
        if query and self._semantic and self._semantic.is_loaded:
            query_emb = self._semantic.embed(query)
            if query_emb is not None:
                with sqlite3.connect(DB_PATH) as conn:
                    sem_rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """SELECT pattern_name, pattern_type, description,
                                  success_count, fail_count, success_rate, steps, embedding
                           FROM procedural_memory
                           WHERE tenant_id=?
                           ORDER BY success_rate DESC LIMIT 100""",
                        (self._tenant_id,)).fetchall()
                for r in sem_rows:
                    cache_emb = self._deserialize_embedding(r[7])
                    if cache_emb is not None:
                        sim = self._semantic.similarity(query_emb, cache_emb)
                        if sim >= 0.5:
                            names = {x["pattern_name"] for x in results}
                            if r[0] not in names:
                                results.append({"pattern_name": r[0], "pattern_type": r[1], "description": r[2], "success_count": r[3], "fail_count": r[4], "success_rate": r[5], "steps": json.loads(r[6] or "[]"), "similarity": sim})
        return results[:limit]

    # ================================================================
    #  6. PROJECT MEMORY (project continuity, tenant-aware)
    # ================================================================

    def save_project(self, project_name: str, project_type: str = "",
                     description: str = "", path: str = "", status: str = "active",
                     entities: Optional[List[str]] = None, endpoints: Optional[List[str]] = None,
                     config: Optional[Dict[str, Any]] = None, notes: str = ""):
        """Guarda/actualiza el estado de un proyecto generado (tenant-aware)."""
        entities = entities or []
        endpoints = endpoints or []
        config = config or {}
        entities_json = json.dumps(entities)
        endpoints_json = json.dumps(endpoints)
        config_json = json.dumps(config)
        with sqlite3.connect(DB_PATH) as conn:
            existing = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT id FROM project_memory WHERE project_name=? AND client_id=? AND tenant_id=?",
                (project_name, self._client_id, self._tenant_id)
            ).fetchone()
            if existing:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE project_memory
                       SET project_type=?, description=?, path=?, status=?,
                           entities=?, endpoints=?, config=?, updated_at=?, notes=?
                       WHERE project_name=? AND client_id=? AND tenant_id=?""",
                    (project_type, description, path, status, entities_json,
                     endpoints_json, config_json, time.time(), notes,
                     project_name, self._client_id, self._tenant_id)
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO project_memory
                       (project_name, project_type, description, path, status,
                        entities, endpoints, config, created_at, updated_at,
                        notes, client_id, tenant_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (project_name, project_type, description, path, status,
                     entities_json, endpoints_json, config_json, time.time(),
                     time.time(), notes, self._client_id, self._tenant_id)
                )

    def get_project(self, project_name: str) -> Optional[Dict[str, Any]]:
        """Obtiene el estado de un proyecto (tenant-scoped)."""
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT project_name, project_type, description, path, status,
                          entities, endpoints, config, created_at, updated_at, notes
                   FROM project_memory
                   WHERE project_name=? AND client_id=? AND tenant_id=?""",
                (project_name, self._client_id, self._tenant_id)
            ).fetchone()
        if not row: return None
        return {"project_name": row[0], "project_type": row[1], "description": row[2], "path": row[3], "status": row[4], "entities": json.loads(row[5] or "[]"), "endpoints": json.loads(row[6] or "[]"), "config": json.loads(row[7] or "{}"), "created_at": row[8], "updated_at": row[9], "notes": row[10]}

    def list_projects(self, status: str = "") -> List[Dict[str, Any]]:
        """Lista todos los proyectos (tenant-scoped)."""
        with sqlite3.connect(DB_PATH) as conn:
            if status:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT project_name, project_type, description, path, status,
                              created_at, updated_at
                       FROM project_memory
                       WHERE status=? AND client_id=? AND tenant_id=?
                       ORDER BY updated_at DESC""",
                    (status, self._client_id, self._tenant_id)
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT project_name, project_type, description, path, status,
                              created_at, updated_at
                       FROM project_memory
                       WHERE client_id=? AND tenant_id=?
                       ORDER BY updated_at DESC""",
                    (self._client_id, self._tenant_id)
                ).fetchall()
        return [{"project_name": r[0], "project_type": r[1], "description": r[2], "path": r[3], "status": r[4], "created_at": r[5], "updated_at": r[6]} for r in rows]

    # ================================================================
    #  ENHANCED STATS (tenant-scoped)
    # ================================================================

    @property
    def enhanced_stats(self) -> Dict[str, Any]:
        """Estadisticas completas de todas las memorias (tenant-scoped)."""
        with sqlite3.connect(DB_PATH) as conn:
            cache_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM semantic_cache WHERE tenant_id=?",
                (self._tenant_id,)
            ).fetchone()[0]
            ltm_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM long_term_memory WHERE tenant_id=?",
                (self._tenant_id,)
            ).fetchone()[0]
            episodic_count = 0
            procedural_count = 0
            project_count = 0
            try:
                episodic_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM episodic_memory WHERE tenant_id=?",
                    (self._tenant_id,)
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pass
            try:
                procedural_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM procedural_memory WHERE tenant_id=?",
                    (self._tenant_id,)
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pass
            try:
                project_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM project_memory WHERE tenant_id=?",
                    (self._tenant_id,)
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pass
        with self._working_lock:
            working_size = len(self._working_memory)
        return {
            "session_id": self._session_id,
            "tenant_id": self._tenant_id,
            "client_id": self._client_id,
            "working_memory_size": working_size,
            "semantic_cache_size": cache_count,
            "long_term_memory_size": ltm_count,
            "episodic_memory_size": episodic_count,
            "procedural_memory_size": procedural_count,
            "project_memory_size": project_count,
            "semantic_engine_available": self._semantic is not None and self._semantic.is_loaded,
        }
