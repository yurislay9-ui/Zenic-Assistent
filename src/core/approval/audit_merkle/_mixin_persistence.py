"""
Audit Merkle — Persistence Mixin.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from typing import Any, List, Optional

from ._types import AuditRecord, AuditEventType, GENESIS_HASH, _MAX_RETRIES, _RETRY_DELAY

logger = logging.getLogger(__name__)


class AuditMerklePersistenceMixin:
    """Persistence helpers for ApprovalAuditMerkle."""

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the audit records table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS audit_records (
                    record_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL DEFAULT '',
                    actor_name TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '{}',
                    content_hash TEXT NOT NULL,
                    previous_hash TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_audit_request
                ON audit_records(request_id, timestamp ASC)
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_audit_hash
                ON audit_records(content_hash)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Private Helpers ────────────────────────────────────

    def _get_last_hash(self) -> str:
        """Get the content_hash of the most recent record (for chaining)."""
        def _do_query() -> str:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """SELECT content_hash FROM audit_records
                   ORDER BY timestamp DESC LIMIT 1""",
            ).fetchone()
            conn.close()
            if row:
                return row[0]
            return GENESIS_HASH

        return self._with_retry(_do_query, fallback=GENESIS_HASH)

    @staticmethod
    def _compute_content_hash(record: AuditRecord, previous_hash: str) -> str:
        """Compute the SHA-256 content hash for a record."""
        payload = json.dumps({
            "request_id": record.request_id,
            "event_type": record.event_type.value if isinstance(record.event_type, AuditEventType) else record.event_type,
            "actor_id": record.actor_id,
            "actor_name": record.actor_name,
            "details": record.details,
            "previous_hash": previous_hash,
            "timestamp": record.timestamp,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _persist_record(self, record: AuditRecord, *, insert: bool) -> None:
        """Insert or update an audit record in the database."""
        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            if insert:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """INSERT INTO audit_records
                       (record_id, request_id, event_type, actor_id,
                        actor_name, details, content_hash, previous_hash,
                        timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.record_id,
                        record.request_id,
                        record.event_type.value,
                        record.actor_id,
                        record.actor_name,
                        json.dumps(record.details),
                        record.content_hash,
                        record.previous_hash,
                        record.timestamp,
                    ),
                )
            else:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """UPDATE audit_records SET
                       details=?, content_hash=?, previous_hash=?
                       WHERE record_id=?""",
                    (
                        json.dumps(record.details),
                        record.content_hash,
                        record.previous_hash,
                        record.record_id,
                    ),
                )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AuditRecord:
        """Convert a database row to an AuditRecord."""
        return AuditRecord(
            record_id=row["record_id"],
            request_id=row["request_id"],
            event_type=AuditEventType(row["event_type"]),
            actor_id=row["actor_id"] or "",
            actor_name=row["actor_name"] or "",
            details=json.loads(row["details"] or "{}"),
            content_hash=row["content_hash"],
            previous_hash=row["previous_hash"],
            timestamp=row["timestamp"],
        )

    @staticmethod
    def _with_retry(
        fn: Any,
        fallback: Any = None,
        max_retries: int = _MAX_RETRIES,
    ) -> Any:
        """Execute *fn* with retry logic on database errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                logger.warning(
                    "ApprovalAuditMerkle: DB retry %d/%d — %s",
                    attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("ApprovalAuditMerkle: DB error — %s", exc)
                break
        logger.error("ApprovalAuditMerkle: All retries exhausted — %s", last_exc)
        return fallback
