from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class RiskLevel(str, Enum):
    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BlastRadiusReport:
    source_node: str
    affected_nodes: List[str] = field(default_factory=list)
    direct_dependents: List[str] = field(default_factory=list)
    transitive_dependents: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.NEGLIGIBLE
    blast_radius_size: int = 0
    recommendations: List[str] = field(default_factory=list)


@dataclass
class RiskPropagationReport:
    effective_risks: Dict[str, float] = field(default_factory=dict)
    max_effective_risk: float = 0.0
    high_risk_nodes: List[str] = field(default_factory=list)
    risk_paths: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class CriticalPathReport:
    critical_path: List[str] = field(default_factory=list)
    total_duration_ms: int = 0
    is_on_critical_path: Dict[str, bool] = field(default_factory=dict)


@dataclass
class CompositeRiskReport:
    blast_radius: BlastRadiusReport = field(default_factory=BlastRadiusReport)
    propagation: RiskPropagationReport = field(default_factory=RiskPropagationReport)
    critical_path: CriticalPathReport = field(default_factory=CriticalPathReport)
    overall_risk_score: float = 0.0
    summary: str = ""
