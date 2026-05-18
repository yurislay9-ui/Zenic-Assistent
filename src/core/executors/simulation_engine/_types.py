"""
Simulation Engine — Data models and utility functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SimulationResult:
    """Result of simulating a DAG or a single dispatch.

    Attributes:
        dag_id: Identifier of the simulated DAG (or generated ID
            for single-action simulations).
        nodes_simulated: Number of DAG nodes that were simulated.
        total_duration_ms: Wall-clock duration of the simulation
            in milliseconds.
        simulated_actions: List of dry-run operations recorded
            during the simulation.
        estimated_impacts: List of dictionaries summarising the
            estimated impact of each simulated node.
        would_succeed: Whether the full pipeline *would* succeed
            if executed for real.
        node_results: Per-node result dictionary mapping node ID
            to its simulated result.
    """

    dag_id: str
    nodes_simulated: int = 0
    total_duration_ms: float = 0.0
    simulated_actions: List[Any] = field(default_factory=list)  # List[DryRunOperation]
    estimated_impacts: List[Dict[str, Any]] = field(default_factory=list)
    would_succeed: bool = True
    node_results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "dag_id": self.dag_id,
            "nodes_simulated": self.nodes_simulated,
            "total_duration_ms": self.total_duration_ms,
            "simulated_actions": [
                op.to_dict() if hasattr(op, "to_dict") else str(op)
                for op in self.simulated_actions
            ],
            "estimated_impacts": self.estimated_impacts,
            "would_succeed": self.would_succeed,
            "node_results": self.node_results,
        }


@dataclass
class ScenarioComparison:
    """Result of comparing two simulation scenarios.

    Attributes:
        scenario_a_result: Simulation result for scenario A.
        scenario_b_result: Simulation result for scenario B.
        differences: List of dictionaries describing the
            differences between the two scenarios.
        recommendation: Human-readable recommendation string.
    """

    scenario_a_result: SimulationResult
    scenario_b_result: SimulationResult
    differences: List[Dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "scenario_a": self.scenario_a_result.to_dict(),
            "scenario_b": self.scenario_b_result.to_dict(),
            "differences": self.differences,
            "recommendation": self.recommendation,
        }


def extract_risk_score(result: SimulationResult) -> float:
    """Extract the maximum risk score from a SimulationResult."""
    max_score = 0.0
    for impact in result.estimated_impacts:
        if isinstance(impact, dict):
            score = impact.get("risk_score", 0.0)
            if isinstance(score, (int, float)):
                max_score = max(max_score, float(score))
    return max_score
