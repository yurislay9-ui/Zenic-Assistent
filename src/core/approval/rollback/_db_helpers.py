"""
ZENIC-AGENTS — Rollback Manager: Database Helpers

Standalone functions for DB persistence and row conversion,
extracted from RollbackManager to keep the main module under 400 lines.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, List, Optional

from ._snapshots import (
    CompensationAction,
    RollbackRecord,
    RollbackStatus,
    RollbackTrigger,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


# ── Retry Utility ──────────────────────────────────────────

def with_retry(
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
                "RollbackManager: DB retry %d/%d — %s",
                attempt, max_retries, exc,
            )
            if attempt < max_retries:
                time.sleep(_RETRY_DELAY * attempt)
        except Exception as exc:
            last_exc = exc
            logger.error("RollbackManager: DB error — %s", exc)
            break
    logger.error("RollbackManager: All retries exhausted — %s", last_exc)
    return fallback


# ── Time Utility ───────────────────────────────────────────

def now_utc_iso() -> str:
    """Return current UTC time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Row Conversion ─────────────────────────────────────────

def row_to_compensation(row: sqlite3.Row) -> CompensationAction:
    """Convert a database row to a CompensationAction."""
    return CompensationAction(
        action_id=row["action_id"],
        action_type=row["action_type"],
        payload=json.loads(row["payload"] or "{}"),
        description=row["description"] or "",
    )


def row_to_rollback_record(row: sqlite3.Row) -> RollbackRecord:
    """Convert a database row to a RollbackRecord."""
    actions_data = json.loads(row["compensation_actions"] or "[]")
    result_data = json.loads(row["result"]) if row["result"] else None
    return RollbackRecord(
        rollback_id=row["rollback_id"],
        request_id=row["request_id"],
        trigger=RollbackTrigger(row["trigger"]),
        compensation_actions=[CompensationAction.from_dict(a) for a in actions_data],
        status=RollbackStatus(row["status"]),
        executed_at=row["executed_at"],
        result=result_data,
        created_at=row["created_at"],
        merkle_hash=row["merkle_hash"],
    )


# ── DB Initialisation ─────────────────────────────────────

def init_db(db_path: str) -> None:
    """Create the rollback tables if they do not exist."""
    def _do_init() -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE TABLE IF NOT EXISTS compensation_actions (
                action_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                description TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE TABLE IF NOT EXISTS rollback_records (
                rollback_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                trigger TEXT NOT NULL,
                compensation_actions TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'pending',
                executed_at TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                merkle_hash TEXT NOT NULL
            )
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE INDEX IF NOT EXISTS idx_compensation_request
            ON compensation_actions(request_id)
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE INDEX IF NOT EXISTS idx_rollback_request
            ON rollback_records(request_id, created_at DESC)
        """)
        conn.commit()
        conn.close()

    with_retry(_do_init)


# ── Persistence ────────────────────────────────────────────

def persist_compensation(
    db_path: str,
    request_id: str,
    action: CompensationAction,
    *,
    insert: bool,
) -> None:
    """Insert or update a compensation action."""
    def _do_persist() -> None:
        conn = sqlite3.connect(db_path)
        if insert:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO compensation_actions
                   (action_id, request_id, action_type, payload, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    action.action_id,
                    request_id,
                    action.action_type,
                    json.dumps(action.payload),
                    action.description,
                ),
            )
        else:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """UPDATE compensation_actions SET
                   payload=?, description=?
                   WHERE action_id=?""",
                (
                    json.dumps(action.payload),
                    action.description,
                    action.action_id,
                ),
            )
        conn.commit()
        conn.close()

    with_retry(_do_persist)


def persist_rollback_record(
    db_path: str,
    record: RollbackRecord,
    *,
    insert: bool,
) -> None:
    """Insert or update a rollback record."""
    def _do_persist() -> None:
        conn = sqlite3.connect(db_path)
        actions_json = json.dumps([a.to_dict() for a in record.compensation_actions])
        result_json = json.dumps(record.result) if record.result else None

        if insert:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO rollback_records
                   (rollback_id, request_id, trigger,
                    compensation_actions, status, executed_at,
                    result, created_at, merkle_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.rollback_id,
                    record.request_id,
                    record.trigger.value,
                    actions_json,
                    record.status.value,
                    record.executed_at,
                    result_json,
                    record.created_at,
                    record.merkle_hash,
                ),
            )
        else:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """UPDATE rollback_records SET
                   status=?, executed_at=?, result=?,
                   merkle_hash=?
                   WHERE rollback_id=?""",
                (
                    record.status.value,
                    record.executed_at,
                    result_json,
                    record.merkle_hash,
                    record.rollback_id,
                ),
            )
        conn.commit()
        conn.close()

    with_retry(_do_persist)


# ── Queries ────────────────────────────────────────────────

def get_compensations(db_path: str, request_id: str) -> List[CompensationAction]:
    """Get all compensation actions for a request."""
    def _do_query() -> List[CompensationAction]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """SELECT * FROM compensation_actions
               WHERE request_id = ?
               ORDER BY action_id ASC""",
            (request_id,),
        ).fetchall()
        conn.close()
        return [row_to_compensation(r) for r in rows]

    return with_retry(_do_query, fallback=[])


def get_rollback_record_by_id(db_path: str, rollback_id: str) -> Optional[RollbackRecord]:
    """Get a rollback record by ID."""
    def _do_find() -> Optional[RollbackRecord]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            "SELECT * FROM rollback_records WHERE rollback_id = ?",
            (rollback_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return row_to_rollback_record(row)

    return with_retry(_do_find, fallback=None)


def get_rollback_history(db_path: str, request_id: str) -> List[RollbackRecord]:
    """Get all rollback records for a request."""
    def _do_query() -> List[RollbackRecord]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """SELECT * FROM rollback_records
               WHERE request_id = ?
               ORDER BY created_at DESC""",
            (request_id,),
        ).fetchall()
        conn.close()
        return [row_to_rollback_record(r) for r in rows]

    return with_retry(_do_query, fallback=[])
