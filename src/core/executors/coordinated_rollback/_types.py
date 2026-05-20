"""
ZENIC-AGENTS - Coordinated Rollback Types

Enums and data models for coordinated rollback.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────


class ResourceType(str, Enum):
    """Supported resource types for coordinated rollback."""

    DB = "db"
    EMAIL = "email"
    FILE = "file"
    WEBHOOK = "webhook"


class ActionStatus(str, Enum):
    """Lifecycle states of a CoordinatedAction."""

    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


# ──────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────


@dataclass
class ResourceRecord:
    """Tracks a single resource operation within a coordinated action.

    Attributes:
        resource_type: The type of resource (db, email, file, webhook).
        resource_id: Identifier for the specific resource instance
            (e.g. journal_id for DB, backup_path for file).
        rollback_data: Arbitrary data needed for rollback (JSON-serialised).
        compensation_executed: Whether the compensation has been performed.
        created_at: Unix timestamp when this record was created.
    """

    resource_type: ResourceType = ResourceType.DB
    resource_id: str = ""
    rollback_data: Dict[str, Any] = field(default_factory=dict)
    compensation_executed: bool = False
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class CoordinatedAction:
    """Represents a multi-resource action being tracked for rollback.

    Attributes:
        action_id: Unique identifier for the coordinated action.
        tenant_id: Tenant that owns this action.
        records: Ordered list of resource records (rollback is reverse).
        status: Current lifecycle status.
        created_at: Unix timestamp when the action was started.
    """

    action_id: str = ""
    tenant_id: str = ""
    records: List[ResourceRecord] = field(default_factory=list)
    status: ActionStatus = ActionStatus.IN_PROGRESS
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.action_id:
            self.action_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class CoordinatedRollbackResult:
    """Result of a coordinated rollback operation.

    Attributes:
        success: Whether all compensations completed without errors.
        action_id: The action that was rolled back.
        compensations_attempted: Total number of compensations attempted.
        compensations_succeeded: Number that succeeded.
        errors: List of error messages from failed compensations.
    """

    success: bool = False
    action_id: str = ""
    compensations_attempted: int = 0
    compensations_succeeded: int = 0
    errors: List[str] = field(default_factory=list)
