"""
ZENIC-AGENTS - Coordinated Rollback Persistence

SQLite persistence helpers for the CoordinatedRollbackManager.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import List, Optional

from src.core.shared.retry import with_retry
from src.core.executors.coordinated_rollback._types import (
    ActionStatus,
    ResourceType,
    ResourceRecord,
    CoordinatedAction,
)

logger = logging.getLogger(__name__)


def init_db(db_path: str) -> None:
    """Create the SQLite tables if they do not exist."""

    def _do_init() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                CREATE TABLE IF NOT EXISTS coordinated_actions (
                    action_id  TEXT PRIMARY KEY,
                    tenant_id  TEXT NOT NULL,
                    status     TEXT NOT NULL DEFAULT 'in_progress',
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "CREATE INDEX IF NOT EXISTS idx_ca_tenant "
                "ON coordinated_actions(tenant_id)"
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "CREATE INDEX IF NOT EXISTS idx_ca_status "
                "ON coordinated_actions(status)"
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                CREATE TABLE IF NOT EXISTS resource_records (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id             TEXT NOT NULL,
                    resource_type         TEXT NOT NULL,
                    resource_id           TEXT NOT NULL DEFAULT '',
                    rollback_data         TEXT NOT NULL DEFAULT '{}',
                    compensation_executed INTEGER NOT NULL DEFAULT 0,
                    created_at            REAL NOT NULL,
                    FOREIGN KEY (action_id) REFERENCES coordinated_actions(action_id)
                )
                """
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "CREATE INDEX IF NOT EXISTS idx_rr_action "
                "ON resource_records(action_id)"
            )
            conn.commit()
        finally:
            conn.close()

    with_retry(
        _do_init,
        max_retries=3,
        base_delay=0.5,
        label="coordinated_rollback._init_db",
    )
    logger.debug(
        "CoordinatedRollbackManager: schema initialised at %s", db_path
    )


def persist_action(db_path: str, action: CoordinatedAction) -> None:
    """Persist a new CoordinatedAction to SQLite."""

    def _do_persist() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT INTO coordinated_actions
                    (action_id, tenant_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (action.action_id, action.tenant_id, action.status.value, action.created_at),
            )
            conn.commit()
        finally:
            conn.close()

    with_retry(
        _do_persist,
        max_retries=3,
        base_delay=0.5,
        label=f"coordinated_rollback.begin({action.action_id[:12]})",
    )


def add_record(db_path: str, action_id: str, record: ResourceRecord) -> None:
    """Persist a ResourceRecord and attach it to an action."""

    def _do_add() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT INTO resource_records
                    (action_id, resource_type, resource_id,
                     rollback_data, compensation_executed, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    record.resource_type.value,
                    record.resource_id,
                    json.dumps(record.rollback_data, default=str),
                    1 if record.compensation_executed else 0,
                    record.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    with_retry(
        _do_add,
        max_retries=3,
        base_delay=0.5,
        label=f"coordinated_rollback._add_record({action_id[:12]})",
    )


def mark_record_compensated(
    db_path: str,
    action_id: str,
    record: ResourceRecord,
) -> None:
    """Mark a resource record as compensated in SQLite."""

    def _do_mark() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                UPDATE resource_records
                SET compensation_executed = 1
                WHERE action_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                """,
                (
                    action_id,
                    record.resource_type.value,
                    record.resource_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    with_retry(
        _do_mark,
        max_retries=3,
        base_delay=0.5,
        label=f"coordinated_rollback._mark_compensated({action_id[:12]})",
    )


def update_action_status(
    db_path: str,
    action_id: str,
    status: ActionStatus,
) -> None:
    """Update the status of a coordinated action in SQLite."""

    def _do_update() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "UPDATE coordinated_actions SET status = ? WHERE action_id = ?",
                (status.value, action_id),
            )
            conn.commit()
        finally:
            conn.close()

    with_retry(
        _do_update,
        max_retries=3,
        base_delay=0.5,
        label=f"coordinated_rollback._update_status({action_id[:12]})",
    )


def load_action(db_path: str, action_id: str) -> Optional[CoordinatedAction]:
    """Load a CoordinatedAction and all its records from SQLite."""

    def _do_load() -> Optional[CoordinatedAction]:
        conn = sqlite3.connect(db_path)
        try:
            # Load the action
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT action_id, tenant_id, status, created_at "
                "FROM coordinated_actions WHERE action_id = ?",
                (action_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            action = CoordinatedAction(
                action_id=row[0],
                tenant_id=row[1],
                status=ActionStatus(row[2]),
                created_at=row[3],
            )

            # Load all records for this action
            cursor2 = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                SELECT resource_type, resource_id, rollback_data,
                       compensation_executed, created_at
                FROM resource_records
                WHERE action_id = ?
                ORDER BY created_at ASC
                """,
                (action_id,),
            )
            for rec_row in cursor2.fetchall():
                record = ResourceRecord(
                    resource_type=ResourceType(rec_row[0]),
                    resource_id=rec_row[1],
                    rollback_data=json.loads(rec_row[2]) if rec_row[2] else {},
                    compensation_executed=bool(rec_row[3]),
                    created_at=rec_row[4],
                )
                action.records.append(record)

            return action
        finally:
            conn.close()

    return with_retry(
        _do_load,
        max_retries=3,
        base_delay=0.5,
        label=f"coordinated_rollback._load_action({action_id[:12]})",
    )


def list_active_action_ids(db_path: str, tenant_id: str) -> List[str]:
    """List all in-progress action IDs for a tenant."""

    def _do_list() -> List[str]:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                SELECT action_id FROM coordinated_actions
                WHERE tenant_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (tenant_id, ActionStatus.IN_PROGRESS.value),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    return with_retry(
        _do_list,
        max_retries=3,
        base_delay=0.5,
        label="coordinated_rollback.list_active_actions",
    )
