"""
coordinated_rollback._mixin_persistence — Persistence helpers mixin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Optional

from src.core.shared.retry import with_retry
from src.core.executors.coordinated_rollback._types import (
    ActionStatus,
    CoordinatedAction,
    ResourceRecord,
    ResourceType,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PersistenceMixin:
    """Mixin providing SQLite persistence helpers for CoordinatedRollbackManager."""

    # These attributes are provided by the main class; declared for type checkers.
    _db_path: str
    _lock: object

    def _add_record(self, action_id: str, record: ResourceRecord) -> None:
        """Persist a ResourceRecord and attach it to an action."""
        with self._lock:

            def _do_add() -> None:
                conn = sqlite3.connect(self._db_path)
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

    def _mark_record_compensated(
        self,
        action_id: str,
        record: ResourceRecord,
    ) -> None:
        """Mark a resource record as compensated in SQLite."""

        def _do_mark() -> None:
            conn = sqlite3.connect(self._db_path)
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

    def _update_action_status(
        self,
        action_id: str,
        status: ActionStatus,
    ) -> None:
        """Update the status of a coordinated action in SQLite."""

        def _do_update() -> None:
            conn = sqlite3.connect(self._db_path)
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

    def _load_action(self, action_id: str) -> Optional[CoordinatedAction]:
        """Load a CoordinatedAction and all its records from SQLite."""

        def _do_load() -> Optional[CoordinatedAction]:
            conn = sqlite3.connect(self._db_path)
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
