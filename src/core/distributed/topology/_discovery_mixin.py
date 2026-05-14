"""
ZENIC-AGENTS - Cluster Topology: Discovery Mixin

Node discovery, dead node detection, and cleanup methods.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ._types import NodeInfo, NodeState

logger = logging.getLogger(__name__)


class DiscoveryMixin:
    """Mixin providing node discovery and dead node detection for ClusterTopology."""

    async def list_active_nodes(self: Any) -> List[NodeInfo]:
        """
        List all active nodes in the cluster.

        Returns:
            List of NodeInfo for active nodes.
        """
        nodes_data = await self._backend.list_nodes(active_only=True)
        return [NodeInfo.from_dict(d) for d in nodes_data]

    async def list_all_nodes(self: Any) -> List[NodeInfo]:
        """
        List all registered nodes (including potentially dead ones).

        Returns:
            List of NodeInfo for all nodes.
        """
        nodes_data = await self._backend.list_nodes(active_only=False)
        return [NodeInfo.from_dict(d) for d in nodes_data]

    async def find_capable_nodes(self: Any, task_type: str) -> List[NodeInfo]:
        """
        Find nodes capable of handling a specific task type.

        Args:
            task_type: The task type to search for.

        Returns:
            List of active nodes that support the given task type.
        """
        active = await self.list_active_nodes()
        capable = []
        for node in active:
            caps = node.capabilities
            if not isinstance(caps, dict):
                continue
            supported = caps.get("task_types", [])
            if isinstance(supported, list) and task_type in supported:
                capable.append(node)
        return capable

    async def get_node(self: Any, node_id: str) -> Optional[NodeInfo]:
        """
        Get information about a specific node.

        Args:
            node_id: The node to look up.

        Returns:
            NodeInfo, or None if not found.
        """
        all_nodes = await self.list_all_nodes()
        for node in all_nodes:
            if node.node_id == node_id:
                return node
        return None

    async def get_cluster_size(self: Any) -> int:
        """
        Get the number of active nodes in the cluster.

        Returns:
            Active node count.
        """
        active = await self.list_active_nodes()
        return len(active)

    async def detect_dead_nodes(self: Any) -> List[NodeInfo]:
        """
        Find nodes that have missed their heartbeats.

        Returns:
            List of nodes considered dead (no recent heartbeat).
        """
        all_nodes = await self.list_all_nodes()
        now = time.time()
        threshold = self._heartbeat_interval * self.DEAD_THRESHOLD_MULTIPLIER
        dead = []

        for node in all_nodes:
            if node.state in (NodeState.LEAVING, NodeState.DEAD):
                continue
            if now - node.last_heartbeat > threshold:
                dead.append(node)

        return dead

    async def cleanup_dead_nodes(self: Any) -> int:
        """
        Remove dead nodes from the topology.

        Returns:
            Number of nodes removed.
        """
        dead = await self.detect_dead_nodes()
        removed = 0
        for node in dead:
            success = await self._backend.deregister_node(node.node_id)
            if success:
                removed += 1
                logger.info(
                    "ClusterTopology: Removed dead node %s "
                    "(last_heartbeat=%.0fs ago)",
                    node.node_id,
                    time.time() - node.last_heartbeat,
                )
        return removed
