"""Graph introspection mixin for DAGBuilder."""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Set

from ._types import DAGNode, DAGEdge, DAGValidationResult

logger = logging.getLogger(__name__)


class DAGBuilderGraphMixin:
    """Mixin providing graph introspection methods for DAGBuilder.

    These methods assume the host class has ``_nodes``, ``_edges``,
    ``_adjacency``, and ``_reverse_adjacency`` attributes.
    """

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
