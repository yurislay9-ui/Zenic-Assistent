"""
Audit Merkle — Types and Constants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1

GENESIS_HASH = "0" * 64


class AuditEventType(str, Enum):
    """Types of audit events in the HITL system."""
    EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"
    JUSTIFICATION_PROVIDED = "JUSTIFICATION_PROVIDED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    DELEGATION_CREATED = "DELEGATION_CREATED"
    ESCALATION_TRIGGERED = "ESCALATION_TRIGGERED"
    ROLLBACK_EXECUTED = "ROLLBACK_EXECUTED"
    EXPIRY_REVERTED = "EXPIRY_REVERTED"
    UNDO_EXECUTED = "UNDO_EXECUTED"


@dataclass
class AuditRecord:
    """A single record in the audit Merkle chain."""

    record_id: str = ""
    request_id: str = ""
    event_type: AuditEventType = AuditEventType.APPROVAL_REQUESTED
    actor_id: str = ""
    actor_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    previous_hash: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"aud-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "request_id": self.request_id,
            "event_type": self.event_type.value,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "details": self.details,
            "content_hash": self.content_hash,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
        }


@dataclass
class MerkleProof:
    """A Merkle proof for verifying a specific record's inclusion."""

    record_id: str = ""
    root_hash: str = ""
    sibling_hashes: List[str] = field(default_factory=list)
    direction: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "root_hash": self.root_hash,
            "sibling_hashes": self.sibling_hashes,
            "direction": self.direction,
        }
