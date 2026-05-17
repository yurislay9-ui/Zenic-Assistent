from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .types import GraphDomain, KnowledgeEdge, KnowledgeNode, KnowledgeQuery, KnowledgeSearchResult

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "knowledge_graph.sqlite"


def _new_id(prefix: str = "kn") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _retry(func: Any, max_retries: int = 3, base_delay: float = 0.1) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


class KnowledgeGraphEngine:
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

    def query(self, query: KnowledgeQuery) -> KnowledgeSearchResult:
        t0 = time.monotonic()
        nodes: List[KnowledgeNode] = []
        edges: List[KnowledgeEdge] = []

        with self._lock:
            def _search() -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
                conn = sqlite3.connect(self._db_path)
                try:
                    conditions: List[str] = []
                    params: List[Any] = []
                    if query.domain:
                        conditions.append("domain = ?")
                        params.append(query.domain)
                    if query.concept:
                        conditions.append("concept LIKE ?")
                        params.append(f"%{query.concept}%")
                    if query.min_confidence > 0:
                        conditions.append("confidence >= ?")
                        params.append(query.min_confidence)

                    where = " AND ".join(conditions) if conditions else "1=1"
                    sql = f"SELECT * FROM kg_nodes WHERE {where} ORDER BY confidence DESC LIMIT ?"
                    params.append(query.max_results)

                    cursor = conn.execute(sql, params)  # nosemgrep: sqlalchemy-execute-raw-query
                    found_nodes = [self._node_from_row(row) for row in cursor.fetchall()]
                    found_node_ids = {n.id for n in found_nodes}

                    found_edges: List[KnowledgeEdge] = []
                    if found_node_ids:
                        placeholders = ",".join("?" for _ in found_node_ids)
                        edge_sql = (
                            f"SELECT * FROM kg_edges WHERE source_id IN ({placeholders}) "
                            f"OR target_id IN ({placeholders})"
                        )
                        cursor = conn.execute(edge_sql, list(found_node_ids) + list(found_node_ids))  # nosemgrep: sqlalchemy-execute-raw-query
                        found_edges = [self._edge_from_row(row) for row in cursor.fetchall()]

                    if query.tags:
                        found_nodes = [
                            n for n in found_nodes
                            if query.tags.intersection(n.tags)
                        ]
                    return found_nodes, found_edges
                finally:
                    conn.close()

            nodes, edges = _retry(_search)

        elapsed = (time.monotonic() - t0) * 1000
        return KnowledgeSearchResult(
            nodes=nodes, edges=edges,
            total_matches=len(nodes), query_time_ms=round(elapsed, 2),
        )

    def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        with self._lock:
            def _fetch() -> Optional[KnowledgeNode]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute("SELECT * FROM kg_nodes WHERE id = ?", (node_id,))  # nosemgrep: sqlalchemy-execute-raw-query
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    node = self._node_from_row(row)
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE kg_nodes SET access_count = access_count + 1, updated_at = ? WHERE id = ?",
                        (_now_iso(), node_id),
                    )
                    conn.commit()
                    return node
                finally:
                    conn.close()

            return _retry(_fetch)

    def get_neighbors(
        self, node_id: str, direction: str = "both"
    ) -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
        with self._lock:
            def _fetch() -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
                conn = sqlite3.connect(self._db_path)
                try:
                    if direction in ("out", "both"):
                        cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            "SELECT * FROM kg_edges WHERE source_id = ?", (node_id,)
                        )
                        out_edges = [self._edge_from_row(r) for r in cursor.fetchall()]
                    else:
                        out_edges = []

                    if direction in ("in", "both"):
                        cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            "SELECT * FROM kg_edges WHERE target_id = ?", (node_id,)
                        )
                        in_edges = [self._edge_from_row(r) for r in cursor.fetchall()]
                    else:
                        in_edges = []

                    all_edges = out_edges + in_edges
                    neighbor_ids: Set[str] = set()
                    for e in all_edges:
                        if e.source_id != node_id:
                            neighbor_ids.add(e.source_id)
                        if e.target_id != node_id:
                            neighbor_ids.add(e.target_id)

                    neighbor_nodes: List[KnowledgeNode] = []
                    if neighbor_ids:
                        placeholders = ",".join("?" for _ in neighbor_ids)
                        cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            f"SELECT * FROM kg_nodes WHERE id IN ({placeholders})",
                            list(neighbor_ids),
                        )
                        neighbor_nodes = [self._node_from_row(r) for r in cursor.fetchall()]

                    return neighbor_nodes, all_edges
                finally:
                    conn.close()

            return _retry(_fetch)

    def find_path(self, source_id: str, target_id: str, max_depth: int = 10) -> List[str]:
        if source_id == target_id:
            return [source_id]

        with self._lock:
            def _bfs() -> List[str]:
                conn = sqlite3.connect(self._db_path)
                try:
                    adj: Dict[str, List[str]] = {}
                    cursor = conn.execute("SELECT source_id, target_id FROM kg_edges")  # nosemgrep: sqlalchemy-execute-raw-query
                    for s, t in cursor.fetchall():
                        adj.setdefault(s, []).append(t)
                        adj.setdefault(t, []).append(s)

                    visited: Set[str] = {source_id}
                    queue: deque[Tuple[str, List[str]]] = deque([(source_id, [source_id])])

                    while queue:
                        current, path = queue.popleft()
                        if len(path) > max_depth + 1:
                            continue
                        for neighbor in adj.get(current, []):
                            if neighbor == target_id:
                                return path + [neighbor]
                            if neighbor not in visited:
                                visited.add(neighbor)
                                queue.append((neighbor, path + [neighbor]))

                    return []
                finally:
                    conn.close()

            return _retry(_bfs)

    def merge_graph(
        self,
        other_nodes: List[KnowledgeNode],
        other_edges: List[KnowledgeEdge],
    ) -> Dict[str, int]:
        stats: Dict[str, int] = {"nodes_added": 0, "nodes_updated": 0, "edges_added": 0, "edges_skipped": 0}

        with self._lock:
            for node in other_nodes:
                if not node.id:
                    node.id = _new_id("kn")
                existing = self.get_node(node.id)
                if existing is None:
                    self.add_node(node)
                    stats["nodes_added"] += 1
                else:
                    if node.confidence > existing.confidence:
                        node.updated_at = _now_iso()
                        self.add_node(node)
                        stats["nodes_updated"] += 1
                    else:
                        stats["nodes_skipped" if "nodes_skipped" in stats else "nodes_updated"] = stats.get("nodes_skipped", 0) + 0

            for edge in other_edges:
                if not edge.id:
                    edge.id = _new_id("ke")
                result = self.add_edge(edge)
                if result:
                    stats["edges_added"] += 1
                else:
                    stats["edges_skipped"] += 1

        return stats

    def get_subgraph(
        self, center_id: str, depth: int = 2
    ) -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
        with self._lock:
            def _collect() -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
                conn = sqlite3.connect(self._db_path)
                try:
                    visited_nodes: Set[str] = set()
                    visited_edges: Set[str] = set()
                    result_nodes: List[KnowledgeNode] = []
                    result_edges: List[KnowledgeEdge] = []
                    current_level: Set[str] = {center_id}

                    for _ in range(depth + 1):
                        next_level: Set[str] = set()
                        for nid in current_level:
                            if nid in visited_nodes:
                                continue
                            visited_nodes.add(nid)
                            cursor = conn.execute("SELECT * FROM kg_nodes WHERE id = ?", (nid,))  # nosemgrep: sqlalchemy-execute-raw-query
                            row = cursor.fetchone()
                            if row:
                                result_nodes.append(self._node_from_row(row))

                            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                                "SELECT * FROM kg_edges WHERE source_id = ? OR target_id = ?",
                                (nid, nid),
                            )
                            for erow in cursor.fetchall():
                                edge = self._edge_from_row(erow)
                                if edge.id not in visited_edges:
                                    visited_edges.add(edge.id)
                                    result_edges.append(edge)
                                    if edge.source_id not in visited_nodes:
                                        next_level.add(edge.source_id)
                                    if edge.target_id not in visited_nodes:
                                        next_level.add(edge.target_id)

                        current_level = next_level
                        if not current_level:
                            break

                    return result_nodes, result_edges
                finally:
                    conn.close()

            return _retry(_collect)

    def prune_stale(self, max_age_days: int = 90) -> int:
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

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            def _calc() -> Dict[str, Any]:
                conn = sqlite3.connect(self._db_path)
                try:
                    node_count = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]  # nosemgrep: sqlalchemy-execute-raw-query
                    edge_count = conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]  # nosemgrep: sqlalchemy-execute-raw-query

                    domain_counts: Dict[str, int] = {}
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT domain, COUNT(*) FROM kg_nodes GROUP BY domain"
                    )
                    for domain, cnt in cursor.fetchall():
                        domain_counts[domain or "unspecified"] = cnt

                    avg_confidence = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT AVG(confidence) FROM kg_nodes"
                    ).fetchone()[0] or 0.0

                    return {
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "domain_counts": domain_counts,
                        "avg_confidence": round(avg_confidence, 4),
                    }
                finally:
                    conn.close()

            return _retry(_calc)

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

_instance: Optional[KnowledgeGraphEngine] = None
_instance_lock = threading.Lock()


def get_knowledge_graph() -> KnowledgeGraphEngine:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = KnowledgeGraphEngine()
    return _instance


def reset_knowledge_graph() -> None:
    global _instance
    with _instance_lock:
        _instance = None
