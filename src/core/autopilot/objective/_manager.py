"""
ZENIC-AGENTS - Objective Store & Persistence (Phase D1)

SQLite persistence layer for objectives with CRUD operations,
thread safety, and retry logic.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ._scoring import (
    Objective,
    ObjectivePriority,
    ObjectiveStatus,
    ObjectiveTarget,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  RETRY HELPER
# ──────────────────────────────────────────────────────────────

def _retry_db_operation(
    func: Any,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> Any:
    """Execute a function with retry logic for DB operations.

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retries.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ObjectiveStore: DB retry %d/%d after %.2fs — %s",
                attempt + 1, max_retries, delay, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "ObjectiveStore: Unexpected error on retry %d/%d — %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
#  OBJECTIVE STORE
# ──────────────────────────────────────────────────────────────

class ObjectiveStore:
    """SQLite persistence layer for objectives.

    Provides CRUD operations with thread safety and retry logic.
    Table name: _zenic_objectives (prefixed to avoid collisions).
    """

    def __init__(self, db_path: str = "autopilot_objectives.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False

    def _ensure_schema(self) -> None:
        """Create the objectives table if it does not exist."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            def _init() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE TABLE IF NOT EXISTS _zenic_objectives (
                            objective_id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            priority TEXT NOT NULL DEFAULT 'normal',
                            status TEXT NOT NULL DEFAULT 'draft',
                            targets TEXT NOT NULL DEFAULT '[]',
                            deadline TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL DEFAULT '',
                            updated_at TEXT NOT NULL DEFAULT '',
                            tenant_id TEXT NOT NULL DEFAULT '',
                            metadata TEXT NOT NULL DEFAULT '{}',
                            tags TEXT NOT NULL DEFAULT '[]'
                        )
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_obj_status
                        ON _zenic_objectives(status)
                    """)
                    conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                        CREATE INDEX IF NOT EXISTS idx_zenic_obj_tenant
                        ON _zenic_objectives(tenant_id)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_init)
            self._initialized = True
            logger.info("ObjectiveStore: Schema initialized at %s", self._db_path)

    # ── CRUD Operations ─────────────────────────────────────

    def create_objective(self, objective: Objective) -> Objective:
        """Persist a new objective.

        Args:
            objective: The Objective to persist.

        Returns:
            The persisted Objective (with auto-generated fields).
        """
        self._ensure_schema()
        with self._lock:
            data = objective.to_dict()

            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT INTO _zenic_objectives
                           (objective_id, name, description, priority, status,
                            targets, deadline, created_at, updated_at,
                            tenant_id, metadata, tags)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            data["objective_id"],
                            data["name"],
                            data["description"],
                            data["priority"],
                            data["status"],
                            json.dumps(data["targets"]),
                            data["deadline"],
                            data["created_at"],
                            data["updated_at"],
                            data["tenant_id"],
                            json.dumps(data["metadata"]),
                            json.dumps(data["tags"]),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_insert)
            logger.info(
                "ObjectiveStore: Created objective %s (%s)",
                objective.objective_id, objective.name,
            )
            return objective

    def get_objective(self, objective_id: str) -> Optional[Objective]:
        """Get an objective by ID.

        Args:
            objective_id: The unique identifier of the objective.

        Returns:
            The Objective if found, or None.
        """
        self._ensure_schema()
        with self._lock:

            def _fetch() -> Optional[Objective]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT * FROM _zenic_objectives WHERE objective_id = ?",
                        (objective_id,),
                    ).fetchone()
                    if row is None:
                        return None
                    return self._row_to_objective(row)
                finally:
                    conn.close()

            return _retry_db_operation(_fetch)

    def update_objective(self, objective: Objective) -> Objective:
        """Update an existing objective.

        Args:
            objective: The Objective with updated fields.

        Returns:
            The updated Objective.
        """
        self._ensure_schema()
        objective.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            data = objective.to_dict()

            def _update() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """UPDATE _zenic_objectives
                           SET name=?, description=?, priority=?, status=?,
                               targets=?, deadline=?, updated_at=?,
                               tenant_id=?, metadata=?, tags=?
                           WHERE objective_id=?""",
                        (
                            data["name"],
                            data["description"],
                            data["priority"],
                            data["status"],
                            json.dumps(data["targets"]),
                            data["deadline"],
                            data["updated_at"],
                            data["tenant_id"],
                            json.dumps(data["metadata"]),
                            json.dumps(data["tags"]),
                            data["objective_id"],
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry_db_operation(_update)
            logger.info(
                "ObjectiveStore: Updated objective %s", objective.objective_id,
            )
            return objective

    def delete_objective(self, objective_id: str) -> bool:
        """Delete an objective by ID.

        Args:
            objective_id: The unique identifier of the objective.

        Returns:
            True if the objective was deleted, False if not found.
        """
        self._ensure_schema()
        with self._lock:

            def _delete() -> bool:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "DELETE FROM _zenic_objectives WHERE objective_id = ?",
                        (objective_id,),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
                finally:
                    conn.close()

            return _retry_db_operation(_delete)

    def list_objectives(
        self,
        status: Optional[ObjectiveStatus] = None,
        priority: Optional[ObjectivePriority] = None,
        tenant_id: str = "",
        tag: str = "",
        limit: int = 100,
    ) -> List[Objective]:
        """List objectives with optional filters.

        Args:
            status: Filter by status.
            priority: Filter by priority.
            tenant_id: Filter by tenant.
            tag: Filter by tag (matches if tag is in the tags list).
            limit: Maximum number of results.

        Returns:
            A list of matching Objectives.
        """
        self._ensure_schema()
        with self._lock:

            def _list() -> List[Objective]:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                try:
                    conditions: List[str] = []
                    params: List[Any] = []
                    if status is not None:
                        conditions.append("status = ?")
                        params.append(status.value)
                    if priority is not None:
                        conditions.append("priority = ?")
                        params.append(priority.value)
                    if tenant_id:
                        conditions.append("tenant_id = ?")
                        params.append(tenant_id)
                    if tag:
                        conditions.append("tags LIKE ?")
                        params.append(f'%"{tag}"%')
                    where = " WHERE " + " AND ".join(conditions) if conditions else ""
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        f"SELECT * FROM _zenic_objectives{where} "
                        f"ORDER BY created_at DESC LIMIT ?",
                        params + [limit],
                    ).fetchall()
                    return [self._row_to_objective(r) for r in rows]
                finally:
                    conn.close()

            return _retry_db_operation(_list)

    def get_active_objectives(self, tenant_id: str = "") -> List[Objective]:
        """Get all active objectives.

        Args:
            tenant_id: Optional tenant filter.

        Returns:
            A list of active Objectives.
        """
        return self.list_objectives(
            status=ObjectiveStatus.ACTIVE, tenant_id=tenant_id,
        )

    def get_objectives_by_tag(self, tag: str) -> List[Objective]:
        """Get objectives that have a specific tag.

        Args:
            tag: The tag to filter by.

        Returns:
            A list of Objectives with the specified tag.
        """
        return self.list_objectives(tag=tag)

    # ── Row Converter ──────────────────────────────────────

    @staticmethod
    def _row_to_objective(row: sqlite3.Row) -> Objective:
        """Convert a database row to an Objective instance."""
        return Objective(
            objective_id=row["objective_id"],
            name=row["name"],
            description=row["description"],
            priority=ObjectivePriority(row["priority"]),
            status=ObjectiveStatus(row["status"]),
            targets=[
                ObjectiveTarget(**t) for t in json.loads(row["targets"])
            ],
            deadline=row["deadline"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tenant_id=row["tenant_id"],
            metadata=json.loads(row["metadata"]),
            tags=json.loads(row["tags"]),
        )


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_objective_store_instance: Optional[ObjectiveStore] = None
_objective_store_lock = threading.Lock()


def get_objective_store(db_path: str = "autopilot_objectives.sqlite") -> ObjectiveStore:
    """Get or create the global ObjectiveStore instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton ObjectiveStore instance.
    """
    global _objective_store_instance
    with _objective_store_lock:
        if _objective_store_instance is None:
            _objective_store_instance = ObjectiveStore(db_path=db_path)
        return _objective_store_instance


def reset_objective_store() -> None:
    """Reset the global ObjectiveStore instance (for testing)."""
    global _objective_store_instance
    with _objective_store_lock:
        _objective_store_instance = None


__all__ = [
    "ObjectiveStore",
    "get_objective_store",
    "reset_objective_store",
]
