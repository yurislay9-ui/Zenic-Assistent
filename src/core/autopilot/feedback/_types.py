"""Types and constants for feedback."""

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

class FeedbackAction(str, Enum):
    """Action to take based on feedback evaluation."""
    CONTINUE = "continue"
    ADJUST_STRATEGY = "adjust_strategy"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    PAUSE_OBJECTIVE = "pause_objective"
    CHANGE_APPROACH = "change_approach"


# ──────────────────────────────────────────────────────────────
#  DATACLASSES
# ──────────────────────────────────────────────────────────────


@dataclass
class FeedbackCycle:
    """A single evaluation cycle in the closed-loop feedback system.

    Records KPI values before and after an autopilot cycle, along with
    the determined action and analysis.
    """
    cycle_id: str = ""
    objective_id: str = ""
    plan_id: str = ""
    cycle_number: int = 0
    kpi_before: Dict[str, float] = field(default_factory=dict)
    kpi_after: Dict[str, float] = field(default_factory=dict)
    action_taken: FeedbackAction = FeedbackAction.CONTINUE
    analysis: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        """Auto-generate ID and timestamp if not provided."""
        if not self.cycle_id:
            self.cycle_id = f"fb-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def improvement(self) -> float:
        """Calculate average improvement across all KPIs.

        For each metric, improvement is calculated as the movement
        toward the target from before to after. Positive values
        indicate improvement.

        Returns:
            Average improvement across all KPIs.
        """
        if not self.kpi_before or not self.kpi_after:
            return 0.0

        improvements: List[float] = []
        for metric, after_val in self.kpi_after.items():
            before_val = self.kpi_before.get(metric, after_val)
            # Positive delta means value increased
            delta = after_val - before_val
            improvements.append(delta)

        if not improvements:
            return 0.0
        return round(sum(improvements) / len(improvements), 6)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "objective_id": self.objective_id,
            "plan_id": self.plan_id,
            "cycle_number": self.cycle_number,
            "kpi_before": self.kpi_before,
            "kpi_after": self.kpi_after,
            "action_taken": self.action_taken.value,
            "analysis": self.analysis,
            "timestamp": self.timestamp,
        }


