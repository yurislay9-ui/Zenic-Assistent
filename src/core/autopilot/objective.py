"""
ZENIC-AGENTS - Objective Data Model & Persistence (Phase D1)

Objective data model and SQLite persistence for the Autopilot by Objectives
system. Objectives represent business goals like "reduce overdue invoices to <5%"
with measurable targets, priorities, and lifecycle management.

Thread-safe: All public methods guarded by RLock.
Retry logic: DB operations wrapped with 3 retries, base 0.5s backoff.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class ObjectiveStatus(str, Enum):
    """Lifecycle status of an objective."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ObjectivePriority(str, Enum):
    """Priority level of an objective."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class ObjectiveTarget:
    """A measurable target for an objective.

    Example: metric_name="overdue_rate", current_value=0.15,
             target_value=0.05, operator="<"
    """
    metric_name: str
    current_value: float
    target_value: float
    unit: str = ""
    operator: str = "<"  # <, >, <=, >=, ==, !=

    def is_met(self) -> bool:
        """Check if the target condition is satisfied."""
        ops: Dict[str, Any] = {
            "<": lambda c, t: c < t,
            ">": lambda c, t: c > t,
            "<=": lambda c, t: c <= t,
            ">=": lambda c, t: c >= t,
            "==": lambda c, t: c == t,
            "!=": lambda c, t: c != t,
        }
        check = ops.get(self.operator, ops["<"])
        try:
            return bool(check(self.current_value, self.target_value))
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "unit": self.unit,
            "operator": self.operator,
        }


@dataclass
class Objective:
    """A business objective with measurable targets.

    Represents a goal the autopilot system works toward, such as
    "reduce overdue invoices to <5%" or "increase revenue by 20%".
    """
    objective_id: str = ""
    name: str = ""
    description: str = ""
    priority: ObjectivePriority = ObjectivePriority.NORMAL
    status: ObjectiveStatus = ObjectiveStatus.DRAFT
    targets: List[ObjectiveTarget] = field(default_factory=list)
    deadline: str = ""
    created_at: str = ""
    updated_at: str = ""
    tenant_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Auto-generate ID and timestamps if not provided."""
        if not self.objective_id:
            self.objective_id = f"obj-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def progress_percent(self) -> float:
        """Calculate average progress percentage across all targets.

        Returns:
            Float between 0.0 and 100.0 representing how close each
            target is to being met, averaged across all targets.
        """
        if not self.targets:
            return 0.0
        progresses: List[float] = []
        for target in self.targets:
            if target.is_met():
                progresses.append(100.0)
                continue
            diff_total = abs(target.target_value) if abs(target.target_value) > 0 else 1.0
            diff_remaining = abs(target.target_value - target.current_value)
            diff_initial = abs(diff_total + diff_remaining) if diff_total > 0 else 1.0
            progress = max(0.0, min(100.0, (1.0 - diff_remaining / diff_initial) * 100.0))
            progresses.append(progress)
        return round(sum(progresses) / len(progresses), 2)

    def is_overdue(self) -> bool:
        """Check if the objective has passed its deadline."""
        if not self.deadline:
            return False
        try:
            deadline_dt = datetime.fromisoformat(self.deadline)
            now = datetime.now(timezone.utc)
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            return now > deadline_dt
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "objective_id": self.objective_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "targets": [t.to_dict() for t in self.targets],
            "deadline": self.deadline,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tenant_id": self.tenant_id,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Objective:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with objective fields.

        Returns:
            A new Objective instance.
        """
        targets_data = data.get("targets", [])
        targets = [
            ObjectiveTarget(**t) if isinstance(t, dict) else t
            for t in targets_data
        ]
        priority_raw = data.get("priority", "normal")
        status_raw = data.get("status", "draft")
        return cls(
            objective_id=data.get("objective_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            priority=ObjectivePriority(priority_raw) if isinstance(priority_raw, str) else priority_raw,
            status=ObjectiveStatus(status_raw) if isinstance(status_raw, str) else status_raw,
            targets=targets,
            deadline=data.get("deadline", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tenant_id=data.get("tenant_id", ""),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )


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
                    conn.execute("""
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
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_zenic_obj_status
                        ON _zenic_objectives(status)
                    """)
                    conn.execute("""
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
                    conn.execute(
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
                    row = conn.execute(
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
                    conn.execute(
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
                    cursor = conn.execute(
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
                    rows = conn.execute(
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
    "ObjectiveStatus",
    "ObjectivePriority",
    "ObjectiveTarget",
    "Objective",
    "ObjectiveStore",
    "get_objective_store",
    "reset_objective_store",
]
