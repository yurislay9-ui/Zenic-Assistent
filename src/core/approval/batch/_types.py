"""
Batch Approval Engine — Types and Constants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class BatchRequest:
    """Metadata for a batch approval request."""

    batch_id: str = ""
    action_type: str = ""
    action_configs: List[Dict[str, Any]] = field(default_factory=list)
    requested_by: int = 0
    required_role: str = ""
    status: str = "pending"
    total_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    created_at: str = ""
    # Stores the individual request_ids created via ApprovalChain
    request_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.batch_id:
            self.batch_id = f"bat-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.total_count == 0 and self.action_configs:
            self.total_count = len(self.action_configs)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "batch_id": self.batch_id,
            "action_type": self.action_type,
            "action_configs": self.action_configs,
            "requested_by": self.requested_by,
            "required_role": self.required_role,
            "status": self.status,
            "total_count": self.total_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "created_at": self.created_at,
            "request_ids": self.request_ids,
        }


@dataclass
class BatchResult:
    """Result of a batch approve/reject operation."""

    batch_id: str = ""
    total: int = 0
    approved: int = 0
    rejected: int = 0
    errors: List[str] = field(default_factory=list)
    individual_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "approved": self.approved,
            "rejected": self.rejected,
            "errors": self.errors,
            "individual_results": self.individual_results,
        }
