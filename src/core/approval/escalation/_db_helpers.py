"""
Zenic-Agents Asistente - Escalation DB Helpers (Phase 5)

Standalone database/persistence functions extracted from EscalationManager.
These functions accept db_path and other dependencies as parameters
rather than using self.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ._types import (
    EscalationLevel,
    SLAPolicy,
    EscalationSLA,
    _MAX_RETRIES,
    _RETRY_DELAY,
)

logger = logging.getLogger(__name__)


# ── Retry helper ──────────────────────────────────────────

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
                "EscalationManager: DB retry %d/%d — %s",
                attempt, max_retries, exc,
            )
            if attempt < max_retries:
                time.sleep(_RETRY_DELAY * attempt)
        except Exception as exc:
            last_exc = exc
            logger.error("EscalationManager: DB error — %s", exc)
            break
    logger.error("EscalationManager: All retries exhausted — %s", last_exc)
    return fallback


# ── Row conversion ────────────────────────────────────────

def row_to_escalation_sla(row: sqlite3.Row) -> EscalationSLA:
    """Convert a database row to an EscalationSLA."""
    return EscalationSLA(
        request_id=row["request_id"],
        current_level=EscalationLevel(row["current_level"]),
        target_role=row["target_role"],
        sla_deadline=row["sla_deadline"],
        breached=bool(row["breached"]),
        auto_escalated=bool(row["auto_escalated"]),
        escalated_at=row["escalated_at"],
    )


# ── DB Initialisation ─────────────────────────────────────

def init_db(db_path: str) -> None:
    """Create the escalation tables if they do not exist."""
    def _do_init() -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE TABLE IF NOT EXISTS sla_policies (
                level INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                max_response_time_ms INTEGER NOT NULL,
                auto_escalate INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE TABLE IF NOT EXISTS escalation_slas (
                request_id TEXT PRIMARY KEY,
                current_level INTEGER NOT NULL DEFAULT 0,
                target_role TEXT NOT NULL,
                sla_deadline TEXT NOT NULL,
                breached INTEGER NOT NULL DEFAULT 0,
                auto_escalated INTEGER NOT NULL DEFAULT 0,
                escalated_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE TABLE IF NOT EXISTS escalation_history (
                history_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                from_level INTEGER NOT NULL,
                to_level INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                escalated_by TEXT NOT NULL DEFAULT '',
                escalated_at TEXT NOT NULL
            )
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE INDEX IF NOT EXISTS idx_escalation_sla_deadline
            ON escalation_slas(sla_deadline, breached)
        """)
        conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
            CREATE INDEX IF NOT EXISTS idx_escalation_history_request
            ON escalation_history(request_id, escalated_at DESC)
        """)
        conn.commit()
        conn.close()

    with_retry(_do_init)


# ── SLA Policy persistence ────────────────────────────────

def load_sla_policies(
    db_path: str,
    sla_policies: Dict[EscalationLevel, SLAPolicy],
) -> None:
    """Load SLA policies from the database, overriding defaults.

    Mutates *sla_policies* in place.
    """
    def _do_load() -> None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM sla_policies").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
        conn.close()
        for row in rows:
            level = EscalationLevel(row["level"])
            sla_policies[level] = SLAPolicy(
                level=level,
                role=row["role"],
                max_response_time_ms=row["max_response_time_ms"],
                auto_escalate=bool(row["auto_escalate"]),
            )

    with_retry(_do_load)


def persist_sla_policy(db_path: str, policy: SLAPolicy) -> None:
    """Persist an SLA policy to the database."""
    def _do_persist() -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """INSERT OR REPLACE INTO sla_policies
               (level, role, max_response_time_ms, auto_escalate)
               VALUES (?, ?, ?, ?)""",
            (
                policy.level.value,
                policy.role,
                policy.max_response_time_ms,
                int(policy.auto_escalate),
            ),
        )
        conn.commit()
        conn.close()

    with_retry(_do_persist)


# ── Escalation SLA persistence ────────────────────────────

def persist_escalation_sla(
    db_path: str,
    sla: EscalationSLA,
    *,
    insert: bool,
) -> None:
    """Insert or update an escalation SLA record."""
    def _do_persist() -> None:
        conn = sqlite3.connect(db_path)
        if insert:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO escalation_slas
                   (request_id, current_level, target_role, sla_deadline,
                    breached, auto_escalated, escalated_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sla.request_id,
                    sla.current_level.value,
                    sla.target_role,
                    sla.sla_deadline,
                    int(sla.breached),
                    int(sla.auto_escalated),
                    sla.escalated_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        else:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """UPDATE escalation_slas SET
                   current_level=?, target_role=?, sla_deadline=?,
                   breached=?, auto_escalated=?, escalated_at=?
                   WHERE request_id=?""",
                (
                    sla.current_level.value,
                    sla.target_role,
                    sla.sla_deadline,
                    int(sla.breached),
                    int(sla.auto_escalated),
                    sla.escalated_at,
                    sla.request_id,
                ),
            )
        conn.commit()
        conn.close()

    with_retry(_do_persist)


# ── Escalation history ────────────────────────────────────

def record_escalation_history(
    db_path: str,
    request_id: str,
    from_level: EscalationLevel,
    to_level: EscalationLevel,
    reason: str,
    escalated_by: str,
) -> None:
    """Record an escalation event in the history table."""
    history_id = f"esh-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    def _do_record() -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """INSERT INTO escalation_history
               (history_id, request_id, from_level, to_level,
                reason, escalated_by, escalated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                history_id,
                request_id,
                from_level.value,
                to_level.value,
                reason,
                escalated_by,
                now,
            ),
        )
        conn.commit()
        conn.close()

    with_retry(_do_record)


# ── Query helpers ─────────────────────────────────────────

def find_escalation_sla(
    db_path: str,
    request_id: str,
) -> Optional[EscalationSLA]:
    """Find an escalation SLA by request ID."""
    def _do_find() -> Optional[EscalationSLA]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            "SELECT * FROM escalation_slas WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return row_to_escalation_sla(row)

    return with_retry(_do_find, fallback=None)


def get_active_slas(db_path: str) -> List[EscalationSLA]:
    """Get all active (non-breached) SLA records."""
    def _do_query() -> List[EscalationSLA]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """SELECT * FROM escalation_slas
               WHERE breached = 0
               ORDER BY sla_deadline ASC""",
        ).fetchall()
        conn.close()
        return [row_to_escalation_sla(r) for r in rows]

    return with_retry(_do_query, fallback=[])


def get_escalation_history_rows(
    db_path: str,
    request_id: str,
) -> List[Dict[str, Any]]:
    """Get the escalation history for a request as a list of dicts."""
    def _do_query() -> List[Dict[str, Any]]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """SELECT * FROM escalation_history
               WHERE request_id = ?
               ORDER BY escalated_at ASC""",
            (request_id,),
        ).fetchall()
        conn.close()
        return [
            {
                "history_id": r["history_id"],
                "request_id": r["request_id"],
                "from_level": r["from_level"],
                "to_level": r["to_level"],
                "reason": r["reason"],
                "escalated_by": r["escalated_by"],
                "escalated_at": r["escalated_at"],
            }
            for r in rows
        ]

    return with_retry(_do_query, fallback=[])
