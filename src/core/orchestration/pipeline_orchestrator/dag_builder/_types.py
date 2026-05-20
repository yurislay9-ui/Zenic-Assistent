"""Types and constants for dag_builder."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class NodeStatus(str, Enum):
    """Status of a DAG node."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"



@dataclass
class DAGNode:
    """
    A node in the DAG representing a pipeline step.

    Attributes:
        node_id: Unique identifier for this node.
        name: Human-readable name.
        node_type: Categorization of the node (e.g. 'transform', 'validate').
        config: Arbitrary configuration for the step.
        status: Current execution status.
        metadata: Additional metadata for observability.
    """
    node_id: str
    name: str = ""
    node_type: str = "generic"
    config: Dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("DAGNode node_id must not be empty")
        if not self.name:
            self.name = self.node_id



@dataclass
class DAGEdge:
    """
    A directed edge in the DAG representing a dependency.

    Attributes:
        source_id: The upstream node ID.
        target_id: The downstream node ID.
        edge_type: Type of dependency (e.g. 'data', 'control').
        label: Optional human-readable label.
    """
    source_id: str
    target_id: str
    edge_type: str = "data"
    label: str = ""

    def __post_init__(self) -> None:
        if not self.source_id or not self.target_id:
            raise ValueError("DAGEdge source_id and target_id must not be empty")



@dataclass
class DAGValidationResult:
    """
    Result of DAG validation.

    Attributes:
        is_valid: Whether the DAG passes all validation checks.
        errors: List of error descriptions.
        warnings: List of warning descriptions.
        cycles: List of detected cycles (each cycle is a list of node IDs).
        orphan_nodes: Node IDs with no incoming or outgoing edges.
    """
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    orphan_nodes: List[str] = field(default_factory=list)
