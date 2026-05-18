"""
Zenic-Agents Asistente - Escalation Types (Phase 5)

SLA-based auto-escalation types and constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1


class EscalationLevel(int, Enum):
    """Escalation hierarchy levels."""
    L0_DIRECT = 0
    L1_TEAM_LEAD = 1
    L2_DIRECTOR = 2
    L3_C_SUITE = 3


@dataclass
class SLAPolicy:
    """SLA policy for an escalation level."""

    level: EscalationLevel = EscalationLevel.L0_DIRECT
    role: str = "reviewer"
    max_response_time_ms: int = 3600000  # 60 minutes in ms
    auto_escalate: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "level": self.level.value,
            "role": self.role,
            "max_response_time_ms": self.max_response_time_ms,
            "auto_escalate": self.auto_escalate,
        }


@dataclass
class EscalationSLA:
    """Tracks the SLA state for a specific approval request."""

    request_id: str = ""
    current_level: EscalationLevel = EscalationLevel.L0_DIRECT
    target_role: str = "reviewer"
    sla_deadline: str = ""
    breached: bool = False
    auto_escalated: bool = False
    escalated_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id is required")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "request_id": self.request_id,
            "current_level": self.current_level.value,
            "target_role": self.target_role,
            "sla_deadline": self.sla_deadline,
            "breached": self.breached,
            "auto_escalated": self.auto_escalated,
            "escalated_at": self.escalated_at,
        }

    def is_breached(self) -> bool:
        """Check if the SLA has been breached based on current time."""
        if not self.sla_deadline:
            return False
        try:
            deadline = datetime.fromisoformat(self.sla_deadline)
            return datetime.now(timezone.utc) > deadline
        except (ValueError, TypeError):
            return False


# Default SLA policies
_DEFAULT_SLA_POLICIES: Dict[EscalationLevel, SLAPolicy] = {
    EscalationLevel.L0_DIRECT: SLAPolicy(
        level=EscalationLevel.L0_DIRECT,
        role="reviewer",
        max_response_time_ms=60 * 60 * 1000,  # 60 min
        auto_escalate=True,
    ),
    EscalationLevel.L1_TEAM_LEAD: SLAPolicy(
        level=EscalationLevel.L1_TEAM_LEAD,
        role="team_lead",
        max_response_time_ms=120 * 60 * 1000,  # 120 min
        auto_escalate=True,
    ),
    EscalationLevel.L2_DIRECTOR: SLAPolicy(
        level=EscalationLevel.L2_DIRECTOR,
        role="director",
        max_response_time_ms=240 * 60 * 1000,  # 240 min
        auto_escalate=True,
    ),
    EscalationLevel.L3_C_SUITE: SLAPolicy(
        level=EscalationLevel.L3_C_SUITE,
        role="c_suite",
        max_response_time_ms=0,  # No limit
        auto_escalate=False,
    ),
}
