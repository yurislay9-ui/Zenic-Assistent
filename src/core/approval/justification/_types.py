"""
Mandatory Justification — Types and Constants.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class JustificationRequirement:
    """Requirements for a justification based on priority level."""

    min_length: int = 20
    require_risk_acknowledgment: bool = False
    require_compliance_check: bool = False
    require_business_justification: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "min_length": self.min_length,
            "require_risk_acknowledgment": self.require_risk_acknowledgment,
            "require_compliance_check": self.require_compliance_check,
            "require_business_justification": self.require_business_justification,
        }


@dataclass
class ApprovalJustification:
    """A justification provided for approving or rejecting a request.

    Justifications are immutable after creation.
    The content_hash provides a SHA-256 fingerprint for tamper detection.
    """

    justification_id: str = ""
    request_id: str = ""
    reason: str = ""
    risk_acknowledgment: bool = False
    compliance_check: bool = False
    business_justification: str = ""
    created_by: str = ""
    created_at: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.justification_id:
            self.justification_id = f"jus-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute SHA-256 hash of the justification content."""
        payload = json.dumps({
            "request_id": self.request_id,
            "reason": self.reason,
            "risk_acknowledgment": self.risk_acknowledgment,
            "compliance_check": self.compliance_check,
            "business_justification": self.business_justification,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "justification_id": self.justification_id,
            "request_id": self.request_id,
            "reason": self.reason,
            "risk_acknowledgment": self.risk_acknowledgment,
            "compliance_check": self.compliance_check,
            "business_justification": self.business_justification,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "content_hash": self.content_hash,
        }
