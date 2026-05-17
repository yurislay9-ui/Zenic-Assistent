"""
DAG Builder — Directed Acyclic Graph construction and validation.

Provides utilities for building pipeline DAGs, validating acyclicity,
computing topological orderings, and identifying critical paths.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "DAGNode",
    "DAGEdge",
    "DAGValidationResult",
    "DAGBuilder",
]


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
#  DAG BUILDER
# ──────────────────────────────────────────────────────────────

class DAGBuilder:
    """
    Builder for constructing and validating pipeline DAGs.

    Usage::

        builder = DAGBuilder()
        builder.add_node("extract", name="Extract Data", node_type="source")
        builder.add_node("transform", name="Transform", node_type="transform")
        builder.add_node("load", name="Load Data", node_type="sink")
        builder.add_edge("extract", "transform")
        builder.add_edge("transform", "load")

        result = builder.validate()
        if result.is_valid:
            order = builder.topological_sort()

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required
        for concurrent access.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, DAGNode] = {}
        self._edges: List[DAGEdge] = []
        self._adjacency: Dict[str, List[str]] = defaultdict(list)
        self._reverse_adjacency: Dict[str, List[str]] = defaultdict(list)

    # ── Node Management ──────────────────────────────────────

    def add_node(
        self,
        node_id: str,
        name: str = "",
        node_type: str = "generic",
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DAGNode:
        """
        Add a node to the DAG.

        Args:
            node_id: Unique identifier for the node.
            name: Human-readable name (defaults to node_id).
            node_type: Categorization of the node.
            config: Step configuration.
            metadata: Additional metadata.

        Returns:
            The created DAGNode.

        Raises:
            ValueError: If node_id already exists.
        """
        if node_id in self._nodes:
            raise ValueError(f"Node '{node_id}' already exists in the DAG")
        node = DAGNode(
            node_id=node_id,
            name=name or node_id,
            node_type=node_type,
            config=config or {},
            metadata=metadata or {},
        )
        self._nodes[node_id] = node
        self._adjacency[node_id]  # ensure key exists
        self._reverse_adjacency[node_id]  # ensure key exists
        logger.debug("DAGBuilder: Added node '%s' (type=%s)", node_id, node_type)
        return node

    def get_node(self, node_id: str) -> Optional[DAGNode]:
        """Retrieve a node by ID, or None if not found."""
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node and all its connected edges.

        Args:
            node_id: The node to remove.

        Returns:
            True if the node was found and removed, False otherwise.
        """
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        # Remove outgoing edges
        for target in list(self._adjacency.get(node_id, [])):
            self._edges = [
                e for e in self._edges
                if not (e.source_id == node_id and e.target_id == target)
            ]
            if target in self._reverse_adjacency and node_id in self._reverse_adjacency[target]:
                self._reverse_adjacency[target].remove(node_id)
        # Remove incoming edges
        for source in list(self._reverse_adjacency.get(node_id, [])):
            self._edges = [
                e for e in self._edges
                if not (e.source_id == source and e.target_id == node_id)
            ]
            if source in self._adjacency and node_id in self._adjacency[source]:
                self._adjacency[source].remove(node_id)
        self._adjacency.pop(node_id, None)
        self._reverse_adjacency.pop(node_id, None)
        logger.debug("DAGBuilder: Removed node '%s'", node_id)
        return True

    # ── Edge Management ──────────────────────────────────────

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "data",
        label: str = "",
    ) -> DAGEdge:
        """
        Add a directed edge (dependency) between two nodes.

        Args:
            source_id: The upstream node ID.
            target_id: The downstream node ID.
            edge_type: Type of dependency.
            label: Optional label.

        Returns:
            The created DAGEdge.

        Raises:
            ValueError: If either node does not exist, or if source == target.
        """
        if source_id not in self._nodes:
            raise ValueError(f"Source node '{source_id}' does not exist")
        if target_id not in self._nodes:
            raise ValueError(f"Target node '{target_id}' does not exist")
        if source_id == target_id:
            raise ValueError("Self-loops are not allowed in a DAG")

        edge = DAGEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            label=label,
        )
        self._edges.append(edge)
        self._adjacency[source_id].append(target_id)
        self._reverse_adjacency[target_id].append(source_id)
        logger.debug(
            "DAGBuilder: Added edge '%s' -> '%s' (type=%s)",
            source_id, target_id, edge_type,
        )
        return edge

    def remove_edge(self, source_id: str, target_id: str) -> bool:
        """Remove an edge. Returns True if found and removed."""
        original_len = len(self._edges)
        self._edges = [
            e for e in self._edges
            if not (e.source_id == source_id and e.target_id == target_id)
        ]
        if source_id in self._adjacency and target_id in self._adjacency[source_id]:
            self._adjacency[source_id].remove(target_id)
        if target_id in self._reverse_adjacency and source_id in self._reverse_adjacency[target_id]:
            self._reverse_adjacency[target_id].remove(source_id)
        removed = len(self._edges) < original_len
        if removed:
            logger.debug("DAGBuilder: Removed edge '%s' -> '%s'", source_id, target_id)
        return removed

    # ── Validation ───────────────────────────────────────────

    def validate(self) -> DAGValidationResult:
        """
        Validate the DAG for correctness.

        Checks:
        1. No cycles (DAG invariant)
        2. No orphan nodes (warning only)
        3. All edge references resolve to existing nodes
        4. No duplicate edges

        Returns:
            DAGValidationResult with validation outcome.
        """
        result = DAGValidationResult()

        # Check for cycles using DFS
        cycles = self._detect_cycles()
        if cycles:
            result.is_valid = False
            result.cycles = cycles
            result.errors.append(
                f"DAG contains {len(cycles)} cycle(s): "
                + "; ".join(" -> ".join(c) for c in cycles)
            )

        # Check for orphan nodes
        connected: Set[str] = set()
        for edge in self._edges:
            connected.add(edge.source_id)
            connected.add(edge.target_id)
        orphans = [nid for nid in self._nodes if nid not in connected]
        if orphans:
            result.warnings.append(
                f"DAG has {len(orphans)} orphan node(s): {', '.join(orphans)}"
            )
            result.orphan_nodes = orphans

        # Check for duplicate edges
        seen_edges: Set[Tuple[str, str]] = set()
        for edge in self._edges:
            key = (edge.source_id, edge.target_id)
            if key in seen_edges:
                result.warnings.append(
                    f"Duplicate edge: '{edge.source_id}' -> '{edge.target_id}'"
                )
            seen_edges.add(key)

        return result

    def _detect_cycles(self) -> List[List[str]]:
        """Detect cycles using DFS with recursion stack."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in self._nodes}
        cycles: List[List[str]] = []
        path: List[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)
            for neighbor in self._adjacency.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle — extract it
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])
                elif color[neighbor] == WHITE:
                    dfs(neighbor)
            path.pop()
            color[node] = BLACK

        for node_id in list(self._nodes.keys()):
            if color.get(node_id, WHITE) == WHITE:
                dfs(node_id)

        return cycles

    # ── Topological Sort ─────────────────────────────────────

    def topological_sort(self) -> List[str]:
        """
        Compute a topological ordering of the DAG.

        Returns:
            List of node IDs in topological order.

        Raises:
            ValueError: If the DAG contains cycles.
        """
        result = self.validate()
        if not result.is_valid:
            raise ValueError("Cannot topologically sort a DAG with cycles")

        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        for edge in self._edges:
            in_degree[edge.target_id] = in_degree.get(edge.target_id, 0) + 1

        queue: List[str] = sorted(
            [nid for nid, deg in in_degree.items() if deg == 0]
        )
        order: List[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in sorted(self._adjacency.get(node, [])):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        if len(order) != len(self._nodes):
            raise ValueError("Topological sort incomplete — DAG may contain cycles")

        return order

    # ── Graph Introspection ──────────────────────────────────

    def get_dependencies(self, node_id: str) -> List[str]:
        """Get the direct dependencies (predecessors) of a node."""
        return list(self._reverse_adjacency.get(node_id, []))

    def get_dependents(self, node_id: str) -> List[str]:
        """Get the direct dependents (successors) of a node."""
        return list(self._adjacency.get(node_id, []))

    def get_all_ancestors(self, node_id: str) -> Set[str]:
        """Get all transitive ancestors (predecessors) of a node."""
        ancestors: Set[str] = set()
        stack = list(self._reverse_adjacency.get(node_id, []))
        while stack:
            n = stack.pop()
            if n not in ancestors:
                ancestors.add(n)
                stack.extend(self._reverse_adjacency.get(n, []))
        return ancestors

    def get_all_descendants(self, node_id: str) -> Set[str]:
        """Get all transitive descendants (successors) of a node."""
        descendants: Set[str] = set()
        stack = list(self._adjacency.get(node_id, []))
        while stack:
            n = stack.pop()
            if n not in descendants:
                descendants.add(n)
                stack.extend(self._adjacency.get(n, []))
        return descendants

    def get_root_nodes(self) -> List[str]:
        """Get nodes with no incoming edges (entry points)."""
        return [
            nid for nid in self._nodes
            if not self._reverse_adjacency.get(nid)
        ]

    def get_leaf_nodes(self) -> List[str]:
        """Get nodes with no outgoing edges (exit points)."""
        return [
            nid for nid in self._nodes
            if not self._adjacency.get(nid)
        ]

    def critical_path(self) -> List[str]:
        """
        Compute the critical path (longest path) through the DAG.

        Uses dynamic programming on the topological order.
        Node weights are read from config.get('weight', 1.0).

        Returns:
            List of node IDs forming the critical path.
        """
        order = self.topological_sort()
        dist: Dict[str, float] = {nid: 0.0 for nid in self._nodes}
        prev: Dict[str, Optional[str]] = {nid: None for nid in self._nodes}

        for nid in order:
            weight = self._nodes[nid].config.get("weight", 1.0)
            for dep in self._reverse_adjacency.get(nid, []):
                candidate = dist[dep] + weight
                if candidate > dist[nid]:
                    dist[nid] = candidate
                    prev[nid] = dep

        # Find the end node with maximum distance
        end_node = max(self._nodes.keys(), key=lambda n: dist[n])

        # Trace back
        path: List[str] = []
        current: Optional[str] = end_node
        while current is not None:
            path.append(current)
            current = prev[current]
        path.reverse()
        return path

    # ── Accessors ────────────────────────────────────────────

    @property
    def nodes(self) -> Dict[str, DAGNode]:
        """Read-only view of all nodes."""
        return dict(self._nodes)

    @property
    def edges(self) -> List[DAGEdge]:
        """Read-only view of all edges."""
        return list(self._edges)

    @property
    def node_count(self) -> int:
        """Number of nodes in the DAG."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the DAG."""
        return len(self._edges)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the DAG to a dictionary."""
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "name": n.name,
                    "node_type": n.node_type,
                    "config": n.config,
                    "status": n.status.value,
                    "metadata": n.metadata,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type,
                    "label": e.label,
                }
                for e in self._edges
            ],
        }

    def __repr__(self) -> str:
        return (
            f"DAGBuilder(nodes={self.node_count}, edges={self.edge_count})"
        )
