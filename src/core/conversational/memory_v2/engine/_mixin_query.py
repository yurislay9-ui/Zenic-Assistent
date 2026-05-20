"""Query and stats mixin for MemoryEngineV2."""

from __future__ import annotations
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional
from .types import MemoryQuery, MemoryRecord, MemorySearchResult, MemoryTier, MemoryType
from ._types import *
from ._helpers import *

logger = logging.getLogger(__name__)


class MemoryQueryMixin:
    """Mixin providing search, stats, and summary methods for MemoryEngineV2."""

    def search(self, query: MemoryQuery) -> MemorySearchResult:
        with self._lock:
            def _search() -> MemorySearchResult:
                conn = sqlite3.connect(self._db_path)
                try:
                    conditions: List[str] = []
                    params: List[Any] = []

                    if query.query_text:
                        conditions.append("content LIKE ?")
                        params.append(f"%{query.query_text}%")

                    if query.tiers:
                        placeholders = ",".join("?" for _ in query.tiers)
                        conditions.append(f"tier IN ({placeholders})")
                        params.extend(t.value for t in query.tiers)

                    if query.types:
                        placeholders = ",".join("?" for _ in query.types)
                        conditions.append(f"mem_type IN ({placeholders})")
                        params.extend(t.value for t in query.types)

                    if query.session_id:
                        conditions.append("session_id = ?")
                        params.append(query.session_id)

                    if query.min_importance > 0:
                        conditions.append("importance >= ?")
                        params.append(query.min_importance)

                    where = " AND ".join(conditions) if conditions else "1=1"
                    sql = (
                        f"SELECT * FROM memory_v2_records WHERE {where} "
                        f"ORDER BY importance DESC, created_at DESC LIMIT ?"
                    )
                    params.append(query.max_results)

                    cursor = conn.execute(sql, params)  # nosemgrep: sqlalchemy-execute-raw-query
                    records = [self._record_from_row(row) for row in cursor.fetchall()]

                    count_sql = f"SELECT COUNT(*) FROM memory_v2_records WHERE {where}"
                    total = conn.execute(count_sql, params[:-1]).fetchone()[0]  # nosemgrep: sqlalchemy-execute-raw-query

                    best = max((r.importance for r in records), default=0.0)
                    return MemorySearchResult(records=records, total=total, best_score=best)
                finally:
                    conn.close()

            return _retry(_search)

    def get_session_summary(self, session_id: str) -> str:
        with self._lock:
            def _summarize() -> str:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM memory_v2_records WHERE session_id = ? "
                        "ORDER BY created_at ASC",
                        (session_id,),
                    )
                    records = [self._record_from_row(row) for row in cursor.fetchall()]
                finally:
                    conn.close()
                return self._generate_summary(records)

            return _retry(_summarize)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            def _calc() -> Dict[str, Any]:
                conn = sqlite3.connect(self._db_path)
                try:
                    total = conn.execute("SELECT COUNT(*) FROM memory_v2_records").fetchone()[0]  # nosemgrep: sqlalchemy-execute-raw-query
                    tier_counts: Dict[str, int] = {}
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT tier, COUNT(*) FROM memory_v2_records GROUP BY tier"
                    )
                    for tier, cnt in cursor.fetchall():
                        tier_counts[tier] = cnt

                    type_counts: Dict[str, int] = {}
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT mem_type, COUNT(*) FROM memory_v2_records GROUP BY mem_type"
                    )
                    for mtype, cnt in cursor.fetchall():
                        type_counts[mtype] = cnt

                    avg_importance = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT AVG(importance) FROM memory_v2_records"
                    ).fetchone()[0] or 0.0

                    return {
                        "total_records": total,
                        "tier_counts": tier_counts,
                        "type_counts": type_counts,
                        "avg_importance": round(avg_importance, 4),
                    }
                finally:
                    conn.close()

            return _retry(_calc)

    @staticmethod
    def _record_from_row(row: Any) -> MemoryRecord:
        expires_at = row[11]
        return MemoryRecord(
            id=row[0],
            tier=MemoryTier(row[1]),
            mem_type=MemoryType(row[2]),
            content=row[3],
            session_id=row[4],
            user_id=row[5],
            importance=row[6],
            access_count=row[7],
            decay_factor=row[8],
            created_at=row[9],
            last_accessed=row[10],
            expires_at=expires_at,
            metadata=json.loads(row[12]) if row[12] else {},
            embedding_hash=row[13],
        )

    @staticmethod
    def _generate_summary(records: List[MemoryRecord]) -> str:
        if not records:
            return ""
        facts = [r.content for r in records if r.mem_type == MemoryType.FACT]
        convos = [r.content for r in records if r.mem_type == MemoryType.CONVERSATION]
        parts: List[str] = []
        if facts:
            parts.append("Facts: " + "; ".join(facts[:10]))
        if convos:
            parts.append("Recent: " + "; ".join(convos[-5:]))
        return " | ".join(parts) if parts else ""
