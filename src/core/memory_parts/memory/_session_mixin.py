"""
SmartMemory — Session Management and Memory Consolidation Mixin.

Session lifecycle, conversation summaries, and memory consolidation.
"""

import hashlib
import logging
import sqlite3
import time
from typing import Any, Dict, List

from ..types import DB_PATH, MemoryEntry, IMPORTANCE_THRESHOLD

logger = logging.getLogger(__name__)


class SessionMixin:
    """Mixin providing session management and consolidation for SmartMemory."""

    def clear_session(self) -> None:
        """Limpia la memoria de trabajo para una nueva sesión."""
        with self._working_lock:
            self._working_memory.clear()
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    def start_session(self) -> str:
        """Inicia una nueva sesión de conversación (tenant-aware)."""
        # End current session if any
        with self._working_lock:
            if self._working_memory:
                pass
            else:
                self._working_memory.clear()
        if self._working_memory:
            self.end_session()
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        with self._working_lock:
            self._working_memory.clear()
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO conversation_sessions 
                   (id, started_at, exchange_count, importance, client_id, tenant_id)
                   VALUES (?, ?, 0, 0.5, ?, ?)""",
                (self._session_id, time.time(), self._client_id, self._tenant_id)
            )
        
        logger.info(
            f"SmartMemory: Session {self._session_id} started "
            f"(tenant='{self._tenant_id}', client='{self._client_id}')"
        )
        return self._session_id

    def end_session(self) -> Dict[str, Any]:
        """Termina la sesión actual y consolida memorias (tenant-aware)."""
        with self._working_lock:
            summary = self.get_conversation_summary()
            exchange_count = len(self._working_memory)
            
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """UPDATE conversation_sessions 
                       SET ended_at=?, summary=?, exchange_count=?, importance=?
                       WHERE id=? AND tenant_id=?""",
                    (time.time(), summary[:1000], exchange_count,
                     max((e.importance for e in self._working_memory), default=0.5),
                     self._session_id, self._tenant_id)
                )
            
            # Snapshot working memory for consolidation (within lock)
            working_snapshot = list(self._working_memory)
        
        # Trigger consolidation (uses snapshot, no lock needed for DB ops)
        self._consolidate_from_snapshot(working_snapshot)
        
        with self._working_lock:
            self._working_memory.clear()
        logger.info(
            f"SmartMemory: Session {self._session_id} ended "
            f"({exchange_count} exchanges, tenant='{self._tenant_id}')"
        )
        return {"session_id": self._session_id, "summary": summary, "exchanges": exchange_count}

    def get_conversation_summary(self, session_id: str = "") -> str:
        """Obtiene un resumen de la conversación de la sesión."""
        sid = session_id or self._session_id
        if not sid:
            return ""
        
        # From working memory if current session (thread-safe read)
        if sid == self._session_id:
            with self._working_lock:
                if self._working_memory:
                    ops = [f"{e.operation}/{e.goal}: {e.query[:50]}" for e in self._working_memory[-10:]]
                    return f"Session {sid}: {' | '.join(ops)}"
        
        # From database for past sessions (tenant-scoped)
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT summary, exchange_count FROM conversation_sessions WHERE id=? AND tenant_id=?",
                (sid, self._tenant_id)
            ).fetchone()
            if row and row[0]:
                return row[0]
        
        return ""

    def consolidate_memories(self) -> Dict[str, int]:
        """
        Consolida memorias: promueve working → long-term, agrupa similares.
        
        Returns dict with counts of items consolidated.
        """
        # Snapshot working memory under lock
        with self._working_lock:
            working_snapshot = list(self._working_memory)
        
        return self._consolidate_from_snapshot(working_snapshot)

    def _consolidate_from_snapshot(self, working_snapshot: List[MemoryEntry]) -> Dict[str, int]:
        """Consolidate from a snapshot of working memory (thread-safe, tenant-aware)."""
        promoted = 0
        consolidated_episodes = 0
        
        # 1. Promote important working memory to long-term
        for entry in working_snapshot:
            if entry.importance >= IMPORTANCE_THRESHOLD:
                # Check if already exists in long-term (avoid duplicates)
                existing = self.find_similar_solutions(entry.query, top_k=1)
                is_duplicate = any(s.get("similarity", 0) > 0.9 for s in existing)
                
                if not is_duplicate:
                    self.save_to_long_term(
                        query=entry.query,
                        solution=entry.response[:500],
                        operation=entry.operation,
                        goal=entry.goal,
                        importance=entry.importance,
                        success=True,
                        tags=[entry.operation, entry.goal, self._session_id],
                    )
                    promoted += 1
        
        # 2. Consolidate episodic memories with same event_type (tenant-scoped)
        with sqlite3.connect(DB_PATH) as conn:
            event_types = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM episodic_memory WHERE tenant_id=? GROUP BY event_type HAVING cnt > 3",
                (self._tenant_id,)
            ).fetchall()
            
            for event_type, count in event_types:
                rows = conn.execute(
                    "SELECT id, description, importance FROM episodic_memory WHERE event_type=? AND tenant_id=? ORDER BY importance DESC",
                    (event_type, self._tenant_id)
                ).fetchall()
                
                if len(rows) > 3:
                    ids_to_remove = [r[0] for r in rows[3:]]
                    descriptions = [r[1][:100] for r in rows[3:]]
                    avg_importance = sum(r[2] for r in rows[3:]) / len(rows[3:])
                    
                    consolidated_desc = f"Consolidated {len(ids_to_remove)} {event_type} events: {'; '.join(descriptions[:3])}"
                    
                    conn.execute(
                        """INSERT INTO episodic_memory 
                           (event_type, description, importance, created_at, client_id, tenant_id)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (event_type, consolidated_desc[:1000], avg_importance, time.time(),
                         self._client_id, self._tenant_id)
                    )
                    
                    conn.execute(
                        f"DELETE FROM episodic_memory WHERE id IN ({','.join('?' * len(ids_to_remove))})",
                        ids_to_remove
                    )
                    consolidated_episodes += len(ids_to_remove)
        
        if promoted > 0 or consolidated_episodes > 0:
            logger.info(f"SmartMemory: Consolidated - promoted={promoted}, episodes_merged={consolidated_episodes}")
        
        return {"promoted_to_long_term": promoted, "episodes_consolidated": consolidated_episodes}

    def get_recent_entries(self, limit: int = 30):
        """Public accessor for recent working memory entries (thread-safe)."""
        with self._working_lock:
            return self._working_memory[:limit]
