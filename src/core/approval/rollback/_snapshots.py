"""
Zenic-Agents Asistente - Rollback Data Models (Phase 5)

Data classes and enums for the rollback/auto-revert system.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class RollbackStatus(str, Enum):
    """Status of a rollback operation."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RollbackTrigger(str, Enum):
    """What triggered the rollback."""
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    ACTION_FAILED = "ACTION_FAILED"
    MANUAL_UNDO = "MANUAL_UNDO"
    COMPLIANCE_VIOLATION = "COMPLIANCE_VIOLATION"


@dataclass
class CompensationAction:
    """A single compensation action to be executed during rollback.

    Compensation actions are registered when an approval is granted.
    They describe what to do if the approved action needs to be undone.
    """

    action_id: str = ""
    action_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.action_id:
            self.action_id = f"cmp-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompensationAction":
        """Deserialize from dictionary."""
        return cls(
            action_id=data.get("action_id", ""),
            action_type=data.get("action_type", ""),
            payload=data.get("payload", {}),
            description=data.get("description", ""),
        )


@dataclass
class RollbackRecord:
    """Record of a rollback operation for a request.

    Contains all compensation actions, execution status, and a
    Merkle hash for immutable audit trail.
    """

    rollback_id: str = ""
    request_id: str = ""
    trigger: RollbackTrigger = RollbackTrigger.MANUAL_UNDO
    compensation_actions: List[CompensationAction] = field(default_factory=list)
    status: RollbackStatus = RollbackStatus.PENDING
    executed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: str = ""
    merkle_hash: str = ""

    def __post_init__(self) -> None:
        if not self.rollback_id:
            self.rollback_id = f"rbk-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.merkle_hash:
            self.merkle_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute SHA-256 Merkle hash of the rollback record."""
        payload = json.dumps({
            "rollback_id": self.rollback_id,
            "request_id": self.request_id,
            "trigger": self.trigger.value if isinstance(self.trigger, RollbackTrigger) else self.trigger,
            "compensation_actions": [a.to_dict() for a in self.compensation_actions],
            "created_at": self.created_at,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "rollback_id": self.rollback_id,
            "request_id": self.request_id,
            "trigger": self.trigger.value if isinstance(self.trigger, RollbackTrigger) else self.trigger,
            "compensation_actions": [a.to_dict() for a in self.compensation_actions],
            "status": self.status.value if isinstance(self.status, RollbackStatus) else self.status,
            "executed_at": self.executed_at,
            "result": self.result,
            "created_at": self.created_at,
            "merkle_hash": self.merkle_hash,
        }


__all__ = [
    "RollbackStatus",
    "RollbackTrigger",
    "CompensationAction",
    "RollbackRecord",
]
