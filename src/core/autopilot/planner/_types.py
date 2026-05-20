"""
ZENIC-AGENTS - Autopilot Planner Data Types

Dataclasses for plan steps and planned actions used throughout
the autopilot planner subsystem.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class PlanStep:
    """A single step in an autopilot plan.

    Each step represents one discrete action the system can take,
    with dependencies on other steps and a risk/impact assessment.
    """
    step_id: str = ""
    name: str = ""
    description: str = ""
    action_type: str = ""
    action_config: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    estimated_impact: float = 0.5
    risk_level: str = "low"
    status: str = "planned"

    def __post_init__(self) -> None:
        """Auto-generate step ID if not provided."""
        if not self.step_id:
            self.step_id = f"step-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "depends_on": self.depends_on,
            "estimated_impact": self.estimated_impact,
            "risk_level": self.risk_level,
            "status": self.status,
        }


@dataclass
class PlannedAction:
    """A complete plan for achieving an objective.

    Contains an ordered list of steps with dependency tracking
    and overall plan status.
    """
    plan_id: str = ""
    objective_id: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    created_at: str = ""
    status: str = "draft"
    priority: int = 0

    def __post_init__(self) -> None:
        """Auto-generate plan ID and timestamp if not provided."""
        if not self.plan_id:
            self.plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "plan_id": self.plan_id,
            "objective_id": self.objective_id,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "status": self.status,
            "priority": self.priority,
        }
