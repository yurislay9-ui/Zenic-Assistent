from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ChaosExperimentState(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FaultType(str, Enum):
    LATENCY = "latency"
    ERROR = "error"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    DEPENDENCY_FAILURE = "dependency_failure"
    DATA_CORRUPTION = "data_corruption"


@dataclass
class FaultInjection:
    fault_type: FaultType
    target: str
    magnitude: float = 1.0
    duration_seconds: int = 30
    probability: float = 1.0
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChaosExperiment:
    id: str
    name: str
    description: str = ""
    injections: List[FaultInjection] = field(default_factory=list)
    steady_state_hypothesis: Dict[str, Any] = field(default_factory=dict)
    state: ChaosExperimentState = ChaosExperimentState.DRAFT
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    rollback_plan: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
