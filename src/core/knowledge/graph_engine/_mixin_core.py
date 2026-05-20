"""Core logic for graph_engine."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
from collections import deque
from typing import Any, Dict, List, Optional, Set

from .types import GraphDomain, KnowledgeEdge, KnowledgeNode, KnowledgeQuery, KnowledgeSearchResult
from ._types import DB_PATH
from ._helpers import _retry, _new_id, _now_iso
from ._mixin_queries import KnowledgeGraphQueriesMixin

logger = logging.getLogger(__name__)

class KnowledgeGraphEngine(KnowledgeGraphQueriesMixin):
    """Thread-safe knowledge graph with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    # ── DB initialization ──────────────────────────────────────

    def _init_db(self) -> None:
        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL DEFAULT '',
                    concept TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    source TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    access_count INTEGER NOT NULL DEFAULT 0,
                    embedding_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_domain ON kg_nodes(domain);
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_concept ON kg_nodes(concept);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_nodes_domain_concept
                    ON kg_nodes(domain, concept);

                CREATE TABLE IF NOT EXISTS kg_edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL DEFAULT '',
                    weight REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (source_id) REFERENCES kg_nodes(id),
                    FOREIGN KEY (target_id) REFERENCES kg_nodes(id)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges(target_id);
            """)
            conn.commit()
            conn.close()

        _retry(_create)

    # ── Node operations ────────────────────────────────────────

    def add_node(self, node: KnowledgeNode) -> str:
        if not node.id:
            node.id = _new_id("kn")
        now = _now_iso()
        if not node.created_at:
            node.created_at = now
        if not node.updated_at:
            node.updated_at = now

        with self._lock:
            def _upsert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO kg_nodes
                           (id, domain, concept, content, tags, confidence, source,
                            created_at, updated_at, access_count, embedding_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(domain, concept) DO UPDATE SET
                           content=excluded.content,
                           tags=excluded.tags,
                           confidence=MAX(confidence, excluded.confidence),
                           source=excluded.source,
                           updated_at=excluded.updated_at,
                           embedding_hash=excluded.embedding_hash""",
                        (
                            node.id, node.domain, node.concept, node.content,
                            json.dumps(sorted(node.tags)), node.confidence, node.source,
                            node.created_at, node.updated_at, node.access_count,
                            node.embedding_hash,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry(_upsert)
            return node.id

    def add_edge(self, edge: KnowledgeEdge) -> str:
        if not edge.id:
            edge.id = _new_id("ke")
        if not edge.created_at:
            edge.created_at = _now_iso()

        with self._lock:
            if not self._node_exists(edge.source_id) or not self._node_exists(edge.target_id):
                logger.warning("Edge references non-existent node, skipping: %s", edge.id)
                return ""
            if self._would_create_cycle(edge.source_id, edge.target_id):
                logger.warning("Edge would create cycle, skipping: %s", edge.id)
                return ""

            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT OR IGNORE INTO kg_edges
                           (id, source_id, target_id, relation_type, weight, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (edge.id, edge.source_id, edge.target_id, edge.relation_type,
                         edge.weight, edge.created_at),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry(_insert)
            return edge.id

    def prune_stale(self, max_age_days: int = 90) -> int:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
        with self._lock:
            def _prune() -> int:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "DELETE FROM kg_nodes WHERE updated_at < ? AND confidence < 0.3",
                        (cutoff,),
                    )
                    deleted = cursor.rowcount
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "DELETE FROM kg_edges WHERE source_id NOT IN (SELECT id FROM kg_nodes) "
                        "OR target_id NOT IN (SELECT id FROM kg_nodes)"
                    )
                    conn.commit()
                    return deleted
                finally:
                    conn.close()

            return _retry(_prune)

    # ── Internal helpers ───────────────────────────────────────

    def _node_exists(self, node_id: str) -> bool:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("SELECT 1 FROM kg_nodes WHERE id = ?", (node_id,))  # nosemgrep: sqlalchemy-execute-raw-query
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def _would_create_cycle(self, source_id: str, target_id: str) -> bool:
        if source_id == target_id:
            return True
        conn = sqlite3.connect(self._db_path)
        try:
            visited: Set[str] = set()
            queue: deque[str] = deque([target_id])
            while queue:
                current = queue.popleft()
                if current == source_id:
                    return True
                if current in visited:
                    continue
                visited.add(current)
                cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT target_id FROM kg_edges WHERE source_id = ?", (current,)
                )
                for (tid,) in cursor.fetchall():
                    if tid not in visited:
                        queue.append(tid)
            return False
        finally:
            conn.close()

    @staticmethod
    def _node_from_row(row: Any) -> KnowledgeNode:
        return KnowledgeNode(
            id=row[0], domain=row[1], concept=row[2], content=row[3],
            tags=set(json.loads(row[4])) if row[4] else set(),
            confidence=row[5], source=row[6],
            created_at=row[7], updated_at=row[8],
            access_count=row[9], embedding_hash=row[10],
        )

    @staticmethod
    def _edge_from_row(row: Any) -> KnowledgeEdge:
        return KnowledgeEdge(
            id=row[0], source_id=row[1], target_id=row[2],
            relation_type=row[3], weight=row[4], created_at=row[5],
        )


# ── Singleton ──────────────────────────────────────────────────
