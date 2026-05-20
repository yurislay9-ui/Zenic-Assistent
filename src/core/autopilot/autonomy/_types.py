"""Types and constants for autonomy."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class AutonomyLevel(str, Enum):
    """Autonomy level of the autopilot system."""
    SUPERVISED = "supervised"
    SEMI_AUTONOMOUS = "semi_autonomous"
    FULL_AUTONOMOUS = "full_autonomous"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────


@dataclass
class AutonomyConfig:
    """Configuration for autopilot autonomy.

    Controls the degree of autonomous action the system can take,
    including risk thresholds for auto-execution vs. human approval.
    """
    level: AutonomyLevel = AutonomyLevel.SEMI_AUTONOMOUS
    objective_id: str = ""
    tenant_id: str = ""
    max_actions_per_cycle: int = 5
    requires_approval_above_risk: float = 0.5
    auto_approve_below_risk: float = 0.2
    notify_on_action: bool = True
    pause_on_exception: bool = True
    escalation_after_cycles: int = 3
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """Set timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def can_auto_execute(self, risk_score: float) -> bool:
        """Check if an action with the given risk score can be auto-executed.

        SUPERVISED: Never auto-execute, always require approval.
        SEMI_AUTONOMOUS: Auto-execute if risk_score < auto_approve_below_risk.
        FULL_AUTONOMOUS: Auto-execute if risk_score < requires_approval_above_risk.

        Args:
            risk_score: Risk score of the action (0.0 to 1.0).

        Returns:
            True if the action can be executed without human approval.
        """
        if self.level == AutonomyLevel.SUPERVISED:
            return False
        if self.level == AutonomyLevel.SEMI_AUTONOMOUS:
            return risk_score < self.auto_approve_below_risk
        if self.level == AutonomyLevel.FULL_AUTONOMOUS:
            return risk_score < self.requires_approval_above_risk
        return False

    def requires_human_approval(self, risk_score: float) -> bool:
        """Check if an action with the given risk score requires human approval.

        Args:
            risk_score: Risk score of the action (0.0 to 1.0).

        Returns:
            True if the action requires human approval before execution.
        """
        return not self.can_auto_execute(risk_score)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "level": self.level.value,
            "objective_id": self.objective_id,
            "tenant_id": self.tenant_id,
            "max_actions_per_cycle": self.max_actions_per_cycle,
            "requires_approval_above_risk": self.requires_approval_above_risk,
            "auto_approve_below_risk": self.auto_approve_below_risk,
            "notify_on_action": self.notify_on_action,
            "pause_on_exception": self.pause_on_exception,
            "escalation_after_cycles": self.escalation_after_cycles,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AutonomyConfig:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with autonomy config fields.

        Returns:
            A new AutonomyConfig instance.
        """
        level_raw = data.get("level", "semi_autonomous")
        return cls(
            level=AutonomyLevel(level_raw) if isinstance(level_raw, str) else level_raw,
            objective_id=data.get("objective_id", ""),
            tenant_id=data.get("tenant_id", ""),
            max_actions_per_cycle=data.get("max_actions_per_cycle", 5),
            requires_approval_above_risk=data.get("requires_approval_above_risk", 0.5),
            auto_approve_below_risk=data.get("auto_approve_below_risk", 0.2),
            notify_on_action=data.get("notify_on_action", True),
            pause_on_exception=data.get("pause_on_exception", True),
            escalation_after_cycles=data.get("escalation_after_cycles", 3),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


