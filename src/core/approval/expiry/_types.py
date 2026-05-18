"""
Expiry Manager — Types and Constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


@dataclass
class ExpiryConfig:
    """Configuration for approval expiration behavior."""

    default_ttl_seconds: int = 3600  # 1 hour
    notification_schedule: List[int] = field(
        default_factory=lambda: [60, 30, 10, 5]
    )  # minutes before expiry
    auto_revert_enabled: bool = True
    revert_action: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "default_ttl_seconds": self.default_ttl_seconds,
            "notification_schedule": self.notification_schedule,
            "auto_revert_enabled": self.auto_revert_enabled,
            "revert_action": self.revert_action,
        }


@dataclass
class ExpiryRecord:
    """Tracks the expiration state of an approval request."""

    request_id: str = ""
    expires_at: str = ""
    reverted_at: Optional[str] = None
    revert_result: Optional[Dict[str, Any]] = None
    notification_sent_at: List[str] = field(default_factory=list)
    status: str = "active"  # active/expired/reverted/cancelled

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id is required")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "request_id": self.request_id,
            "expires_at": self.expires_at,
            "reverted_at": self.reverted_at,
            "revert_result": self.revert_result,
            "notification_sent_at": self.notification_sent_at,
            "status": self.status,
        }

    def is_expired(self) -> bool:
        """Check if the record has expired based on the current time."""
        if self.status != "active":
            return False
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp
        except (ValueError, TypeError):
            return False

    def minutes_remaining(self) -> float:
        """Return minutes remaining until expiry."""
        if not self.expires_at:
            return float("inf")
        try:
            exp = datetime.fromisoformat(self.expires_at)
            delta = exp - datetime.now(timezone.utc)
            return max(0.0, delta.total_seconds() / 60.0)
        except (ValueError, TypeError):
            return 0.0
