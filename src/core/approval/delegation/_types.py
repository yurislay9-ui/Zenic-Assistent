"""
Delegation Manager — Types and Constants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class DelegationRule:
    """A rule that delegates approval authority from one user to another."""

    rule_id: str = ""
    from_user_id: int = 0
    to_user_id: int = 0
    from_role: str = ""
    to_role: str = ""
    active: bool = True
    expires_at: str = ""
    created_at: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = f"del-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def is_active(self) -> bool:
        """Check whether this rule is currently active and not expired."""
        if not self.active:
            return False
        if not self.expires_at:
            return True  # No expiry = always active (while active=True)
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) < exp
        except (ValueError, TypeError):
            return self.active

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "rule_id": self.rule_id,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "from_role": self.from_role,
            "to_role": self.to_role,
            "active": self.active,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass
class DelegationRecord:
    """An actual delegation event (when a rule is applied to a request)."""

    record_id: str = ""
    rule_id: str = ""
    original_approver: int = 0
    delegated_to: int = 0
    action_type: str = ""
    delegated_at: str = ""
    acknowledged: bool = False

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"dlr-{uuid.uuid4().hex[:12]}"
        if not self.delegated_at:
            self.delegated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "rule_id": self.rule_id,
            "original_approver": self.original_approver,
            "delegated_to": self.delegated_to,
            "action_type": self.action_type,
            "delegated_at": self.delegated_at,
            "acknowledged": self.acknowledged,
        }
