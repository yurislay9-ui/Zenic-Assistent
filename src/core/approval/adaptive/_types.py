"""
Adaptive Approval Engine — Types and Constants.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

# Action categories that are NEVER auto-approved
_FINANCIAL_KEYWORDS = ("payment", "financial", "refund", "invoice_pay")
_MAX_RETRIES = 3
_RETRY_DELAY = 0.1  # seconds between retries


@dataclass
class AdaptiveApprovalRecord:
    """Tracks approval history for a user+action_type+config_hash combination."""

    record_id: str = ""
    user_id: int = 0
    action_type: str = ""
    action_config_hash: str = ""
    consecutive_approvals: int = 0
    last_auto_approved: str = ""
    total_auto_approvals: int = 0
    total_manual_approvals: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"adar-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def should_auto_approve(self, threshold: int = 5) -> bool:
        """Return True if consecutive_approvals >= threshold."""
        return self.consecutive_approvals >= threshold

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "action_config_hash": self.action_config_hash,
            "consecutive_approvals": self.consecutive_approvals,
            "last_auto_approved": self.last_auto_approved,
            "total_auto_approvals": self.total_auto_approvals,
            "total_manual_approvals": self.total_manual_approvals,
            "created_at": self.created_at,
        }


def _hash_config(action_config: Dict[str, Any]) -> str:
    """Produce a stable hash of an action config dict."""
    canonical = json.dumps(action_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
