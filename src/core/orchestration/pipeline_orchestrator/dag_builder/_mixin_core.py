"""Core logic for dag_builder."""

from __future__ import annotations
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from ._types import DAGNode, DAGEdge, DAGValidationResult, NodeStatus
from ._mixin_graph import DAGBuilderGraphMixin

logger = logging.getLogger(__name__)


class DAGBuilder(DAGBuilderGraphMixin):
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
