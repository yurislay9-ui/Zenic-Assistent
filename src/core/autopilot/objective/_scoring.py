"""
ZENIC-AGENTS - Objective Data Model & Scoring (Phase D1)

Objective data model, enums, and scoring/progress calculation logic
for the Autopilot by Objectives system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


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


__all__ = [
    "ObjectiveStatus",
    "ObjectivePriority",
    "ObjectiveTarget",
    "Objective",
]
