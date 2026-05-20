"""Core logic for engine."""

from __future__ import annotations
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from .types import ContextWindow, MemoryQuery, MemoryRecord, MemorySearchResult, MemoryTier, MemoryType
from ._types import *
from ._helpers import *
from ._mixin_query import MemoryQueryMixin

logger = logging.getLogger(__name__)

class MemoryEngineV2(MemoryQueryMixin):
    """Thread-safe hierarchical memory engine with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory_v2_records (
                    id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL DEFAULT 'short_term',
                    mem_type TEXT NOT NULL DEFAULT 'conversation',
                    content TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    user_id INTEGER,
                    importance REAL NOT NULL DEFAULT 0.5,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    decay_factor REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL DEFAULT '',
                    last_accessed TEXT NOT NULL DEFAULT '',
                    expires_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    embedding_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_mem_v2_session ON memory_v2_records(session_id);
                CREATE INDEX IF NOT EXISTS idx_mem_v2_tier ON memory_v2_records(tier);
                CREATE INDEX IF NOT EXISTS idx_mem_v2_type ON memory_v2_records(mem_type);
                CREATE INDEX IF NOT EXISTS idx_mem_v2_importance ON memory_v2_records(importance);
                CREATE INDEX IF NOT EXISTS idx_mem_v2_hash ON memory_v2_records(embedding_hash);
            """)
            conn.commit()
            conn.close()

        _retry(_create)

    def store(
        self,
        content: str,
        tier: MemoryTier = MemoryTier.SHORT_TERM,
        mem_type: MemoryType = MemoryType.CONVERSATION,
        session_id: str = "",
        user_id: Optional[int] = None,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not content.strip():
            return ""

        record_id = _new_id("mem")
        now = _now_iso()
        ehash = _content_hash(content)
        meta_json = json.dumps(metadata or {})
        expires = None
        if tier == MemoryTier.EPHEMERAL:
            expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        elif tier == MemoryTier.SHORT_TERM:
            expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()

        with self._lock:
            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO memory_v2_records
                           (id, tier, mem_type, content, session_id, user_id,
                            importance, access_count, decay_factor, created_at,
                            last_accessed, expires_at, metadata, embedding_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1.0, ?, ?, ?, ?, ?)""",
                        (
                            record_id, tier.value, mem_type.value, content,
                            session_id, user_id, importance, now, now,
                            expires, meta_json, ehash,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry(_insert)
        return record_id

    def retrieve(self, record_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            def _fetch() -> Optional[MemoryRecord]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM memory_v2_records WHERE id = ?", (record_id,)
                    )
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE memory_v2_records SET access_count = access_count + 1, "
                        "last_accessed = ? WHERE id = ?",
                        (_now_iso(), record_id),
                    )
                    conn.commit()
                    return self._record_from_row(row)
                finally:
                    conn.close()

            return _retry(_fetch)

    def promote(self, record_id: str, target_tier: MemoryTier) -> bool:
        with self._lock:
            def _promote() -> bool:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT tier FROM memory_v2_records WHERE id = ?", (record_id,)
                    )
                    row = cursor.fetchone()
                    if row is None:
                        return False

                    current_tier = MemoryTier(row[0])
                    if _TIER_ORDER.get(target_tier, 0) <= _TIER_ORDER.get(current_tier, 0):
                        return False

                    now = _now_iso()
                    expires = None
                    if target_tier == MemoryTier.SHORT_TERM:
                        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
                    elif target_tier == MemoryTier.LONG_TERM:
                        expires = None
                    elif target_tier == MemoryTier.PERMANENT:
                        expires = None

                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE memory_v2_records SET tier = ?, last_accessed = ?, expires_at = ? WHERE id = ?",
                        (target_tier.value, now, expires, record_id),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()

            return _retry(_promote)

    def decay(self, max_age_hours: int = 168) -> int:
        cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()
        demoted = 0

        with self._lock:
            def _apply_decay() -> int:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE memory_v2_records SET decay_factor = decay_factor * 0.95 "
                        "WHERE tier != 'permanent' AND last_accessed < ?",
                        (cutoff,),
                    )
                    demote_cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE memory_v2_records SET tier = 'ephemeral' "
                        "WHERE tier = 'short_term' AND decay_factor < 0.3 AND last_accessed < ?",
                        (cutoff,),
                    )
                    demoted = demote_cursor.rowcount

                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "DELETE FROM memory_v2_records "
                        "WHERE tier = 'ephemeral' AND expires_at IS NOT NULL AND expires_at < ?",
                        (_now_iso(),),
                    )
                    conn.commit()
                    return demoted
                finally:
                    conn.close()

            demoted = _retry(_apply_decay)
        return demoted

    def build_context_window(
        self, session_id: str, max_tokens: int = 4096
    ) -> ContextWindow:
        with self._lock:
            def _build() -> ContextWindow:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM memory_v2_records WHERE session_id = ? "
                        "ORDER BY importance DESC, created_at ASC",
                        (session_id,),
                    )
                    all_records = [self._record_from_row(row) for row in cursor.fetchall()]
                finally:
                    conn.close()

                selected: List[MemoryRecord] = []
                token_count = 0
                for rec in all_records:
                    est_tokens = len(rec.content.split()) * 1.3
                    if token_count + est_tokens > max_tokens:
                        continue
                    selected.append(rec)
                    token_count += int(est_tokens)

                summary = self._generate_summary(selected)

                return ContextWindow(
                    id=_new_id("ctx"),
                    session_id=session_id,
                    records=selected,
                    token_count=int(token_count),
                    max_tokens=max_tokens,
                    summary=summary,
                    created_at=_now_iso(),
                )

            return _retry(_build)

    def consolidate(self, session_id: str) -> Dict[str, int]:
        stats: Dict[str, int] = {"merged": 0, "promoted": 0, "removed": 0}

        with self._lock:
            def _consolidate() -> Dict[str, int]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM memory_v2_records WHERE session_id = ? "
                        "ORDER BY embedding_hash, created_at ASC",
                        (session_id,),
                    )
                    records = [self._record_from_row(row) for row in cursor.fetchall()]
                finally:
                    conn.close()

                hash_groups: Dict[str, List[MemoryRecord]] = {}
                for rec in records:
                    hash_groups.setdefault(rec.embedding_hash, []).append(rec)

                for ehash, group in hash_groups.items():
                    if len(group) < 2:
                        continue
                    best = max(group, key=lambda r: r.importance)
                    for rec in group:
                        if rec.id == best.id:
                            continue
                        self._delete_record(conn=None, record_id=rec.id)
                        stats["removed"] += 1
                    stats["merged"] += 1

                for rec in records:
                    if rec.tier == MemoryTier.SHORT_TERM and rec.importance >= 0.8:
                        self.promote(rec.id, MemoryTier.LONG_TERM)
                        stats["promoted"] += 1

                return stats

            result = _consolidate()
            stats.update(result)
        return stats

    def forget(self, record_id: str) -> bool:
        with self._lock:
            return self._delete_record(conn=None, record_id=record_id)

    def _delete_record(self, conn: Optional[sqlite3.Connection], record_id: str) -> bool:
        own_conn = conn is None
        if own_conn:
            conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "DELETE FROM memory_v2_records WHERE id = ?", (record_id,)
            )
            if own_conn:
                conn.commit()
            return cursor.rowcount > 0
        finally:
            if own_conn:
                conn.close()


# ── Singleton ──────────────────────────────────────────────────
