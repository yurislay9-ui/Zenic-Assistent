"""Query mixin for KnowledgeGraphEngine."""

from __future__ import annotations
import json
import logging
import sqlite3
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .types import GraphDomain, KnowledgeEdge, KnowledgeNode, KnowledgeQuery, KnowledgeSearchResult
from ._types import DB_PATH
from ._helpers import _retry, _new_id, _now_iso

logger = logging.getLogger(__name__)


class KnowledgeGraphQueriesMixin:
    """Mixin providing query methods for KnowledgeGraphEngine.

    Expects the host class to have ``_lock`` and ``_db_path``
    attributes, as well as ``_node_from_row`` and ``_edge_from_row``
    static methods.
    """

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
