from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .types import KnowledgeNode

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "knowledge_graph.sqlite"


def _new_id(prefix: str = "sub") -> str:
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


class CrossAgentKnowledgeBus:
    """Thread-safe cross-agent knowledge sharing with pub/sub."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cab_subscriptions (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    callback_filter TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_cab_subs_domain ON cab_subscriptions(domain);
                CREATE INDEX IF NOT EXISTS idx_cab_subs_agent ON cab_subscriptions(agent_id);

                CREATE TABLE IF NOT EXISTS cab_notifications (
                    id TEXT PRIMARY KEY,
                    subscription_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    notified_at TEXT NOT NULL DEFAULT '',
                    delivered INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_cab_notif_sub ON cab_notifications(subscription_id);
            """)
            conn.commit()
            conn.close()

        _retry(_create)

    def publish(
        self,
        domain: str,
        concept: str,
        content: str,
        tags: Set[str],
        source_agent: str,
        confidence: float = 0.5,
    ) -> str:
        from .graph_engine import get_knowledge_graph

        node = KnowledgeNode(
            id=_new_id("kn"),
            domain=domain,
            concept=concept,
            content=content,
            tags=tags,
            confidence=confidence,
            source=source_agent,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        node_id = get_knowledge_graph().add_node(node)
        self.notify_subscribers(domain, node_id)
        return node_id

    def subscribe(
        self,
        domain: str,
        agent_id: str,
        callback_filter: Optional[Dict[str, Any]] = None,
    ) -> str:
        sub_id = _new_id("sub")
        now = _now_iso()
        cb_json = json.dumps(callback_filter or {})

        with self._lock:
            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO cab_subscriptions
                           (id, domain, agent_id, callback_filter, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (sub_id, domain, agent_id, cb_json, now),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry(_insert)
        return sub_id

    def notify_subscribers(self, domain: str, node_id: str) -> int:
        count = 0
        with self._lock:
            def _notify() -> int:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT id FROM cab_subscriptions WHERE domain = ?",
                        (domain,),
                    )
                    sub_ids = [row[0] for row in cursor.fetchall()]
                    now = _now_iso()
                    for sub_id in sub_ids:
                        notif_id = _new_id("notif")
                        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            """INSERT INTO cab_notifications
                               (id, subscription_id, node_id, domain, notified_at, delivered)
                               VALUES (?, ?, ?, ?, ?, 1)""",
                            (notif_id, sub_id, node_id, domain, now),
                        )
                    conn.commit()
                    return len(sub_ids)
                finally:
                    conn.close()

            count = _retry(_notify)
        return count

    def get_subscriptions(self, agent_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            def _fetch() -> List[Dict[str, Any]]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT id, domain, agent_id, callback_filter, created_at "
                        "FROM cab_subscriptions WHERE agent_id = ?",
                        (agent_id,),
                    )
                    results: List[Dict[str, Any]] = []
                    for row in cursor.fetchall():
                        results.append({
                            "id": row[0],
                            "domain": row[1],
                            "agent_id": row[2],
                            "callback_filter": json.loads(row[3]) if row[3] else {},
                            "created_at": row[4],
                        })
                    return results
                finally:
                    conn.close()

            return _retry(_fetch)

    def unsubscribe(self, subscription_id: str) -> bool:
        with self._lock:
            def _delete() -> bool:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "DELETE FROM cab_subscriptions WHERE id = ?",
                        (subscription_id,),
                    )
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "DELETE FROM cab_notifications WHERE subscription_id = ?",
                        (subscription_id,),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
                finally:
                    conn.close()

            return _retry(_delete)

    def propagate_knowledge(
        self,
        source_domain: str,
        target_domain: str,
        max_depth: int = 3,
    ) -> Dict[str, int]:
        from .graph_engine import get_knowledge_graph

        stats: Dict[str, int] = {"propagated": 0, "skipped": 0, "edges_created": 0}
        engine = get_knowledge_graph()

        with self._lock:
            def _propagate() -> Dict[str, int]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT id FROM kg_nodes WHERE domain = ?",
                        (source_domain,),
                    )
                    source_ids = [row[0] for row in cursor.fetchall()]
                finally:
                    conn.close()
                return source_ids

            source_ids = _retry(_propagate)

            visited: Set[str] = set()
            queue: deque[tuple[str, int]] = deque((sid, 0) for sid in source_ids)

            while queue:
                nid, depth = queue.popleft()
                if nid in visited or depth > max_depth:
                    continue
                visited.add(nid)

                node = engine.get_node(nid)
                if node is None:
                    continue

                existing = engine.query(
                    __import__("src.core.knowledge.types", fromlist=["KnowledgeQuery"]).KnowledgeQuery(
                        domain=target_domain, concept=node.concept, max_results=1,
                    )
                )
                if existing.nodes:
                    stats["skipped"] += 1
                    continue

                new_node = KnowledgeNode(
                    id=_new_id("kn"),
                    domain=target_domain,
                    concept=node.concept,
                    content=node.content,
                    tags=node.tags,
                    confidence=node.confidence * 0.9,
                    source=f"propagated:{source_domain}",
                    created_at=_now_iso(),
                    updated_at=_now_iso(),
                )
                new_id = engine.add_node(new_node)
                stats["propagated"] += 1

                if new_id and nid:
                    from .types import KnowledgeEdge
                    edge = KnowledgeEdge(
                        id=_new_id("ke"),
                        source_id=nid,
                        target_id=new_id,
                        relation_type="propagated_to",
                        weight=0.8,
                        created_at=_now_iso(),
                    )
                    eid = engine.add_edge(edge)
                    if eid:
                        stats["edges_created"] += 1

                neighbors, _ = engine.get_neighbors(nid, direction="out")
                for nb in neighbors:
                    if nb.id not in visited:
                        queue.append((nb.id, depth + 1))

        return stats

    def resolve_conflicts(
        self,
        node_ids: List[str],
        strategy: str = "highest_confidence",
    ) -> Optional[KnowledgeNode]:
        from .graph_engine import get_knowledge_graph

        engine = get_knowledge_graph()
        nodes: List[KnowledgeNode] = []
        for nid in node_ids:
            node = engine.get_node(nid)
            if node is not None:
                nodes.append(node)

        if not nodes:
            return None

        if strategy == "highest_confidence":
            return max(nodes, key=lambda n: n.confidence)
        elif strategy == "most_recent":
            return max(nodes, key=lambda n: n.updated_at)
        elif strategy == "most_accessed":
            return max(nodes, key=lambda n: n.access_count)
        else:
            return nodes[0]


# ── Singleton ──────────────────────────────────────────────────

_instance: Optional[CrossAgentKnowledgeBus] = None
_instance_lock = threading.Lock()


def get_cross_agent_bus() -> CrossAgentKnowledgeBus:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CrossAgentKnowledgeBus()
    return _instance


def reset_cross_agent_bus() -> None:
    global _instance
    with _instance_lock:
        _instance = None
