"""
ZENIC-AGENTS - Cluster Topology

Node registration, heartbeat tracking, and cluster topology management.
Provides a real-time view of all active nodes in the distributed system.

Features:
    - Node registration with capabilities
    - Periodic heartbeat with status updates
    - Automatic detection of dead nodes (missed heartbeats)
    - Node capability queries (find workers by task type)
    - Cluster-wide statistics
    - Graceful node departure (deregistration)

Use Cases:
    - Service discovery (find available workers)
    - Load monitoring (track node utilization)
    - Work distribution (route tasks to capable nodes)
    - Failure detection (identify dead nodes)
"""

import logging
import socket
import threading
from typing import Any, Dict, Optional

from .backend import CoordinationBackend
from ._types import NodeInfo, NodeState
from ._lifecycle_mixin import LifecycleMixin
from ._discovery_mixin import DiscoveryMixin

logger = logging.getLogger(__name__)

__all__ = [
    "ClusterTopology",
    "NodeInfo",
    "NodeState",
]


class ClusterTopology(LifecycleMixin, DiscoveryMixin):
    """
    Cluster topology manager for node registration and discovery.

    Each node registers itself on startup, sends periodic heartbeats,
    and deregisters on shutdown. Other nodes can query the topology
    to discover available workers and their capabilities.

    Usage::

        topology = ClusterTopology(
            backend=backend,
            node_info=NodeInfo(
                capabilities={"task_types": ["code_generation", "reasoning"]},
            ),
        )

        # Register this node
        await topology.join()

        # Start background heartbeat
        topology.start_heartbeat()

        # Discover workers
        nodes = await topology.find_capable_nodes("code_generation")

        # Graceful departure
        await topology.leave()
    """

    # How many missed heartbeats before a node is considered dead
    DEAD_THRESHOLD_MULTIPLIER = 3

    def __init__(
        self,
        backend: CoordinationBackend,
        node_info: Optional[NodeInfo] = None,
        heartbeat_interval: float = 10.0,
    ) -> None:
        """
        Initialize the cluster topology manager.

        Args:
            backend: Coordination backend for persistent state.
            node_info: This node's information.
            heartbeat_interval: Seconds between heartbeats.
        """
        self._backend = backend
        self._node_info = node_info or NodeInfo()
        self._heartbeat_interval = heartbeat_interval

        # Ensure IP address is set
        if not self._node_info.ip_address:
            self._node_info.ip_address = self._get_local_ip()

        # Background threads
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._joined = False

    # ----------------------------------------------------------
    #  PROPERTIES / STATS
    # ----------------------------------------------------------

    @property
    def node_info(self) -> NodeInfo:
        """This node's information."""
        return self._node_info

    @property
    def is_joined(self) -> bool:
        """Whether this node is registered in the cluster."""
        return self._joined

    @property
    def stats(self) -> Dict[str, Any]:
        """Topology manager statistics."""
        return {
            "node_id": self._node_info.node_id,
            "hostname": self._node_info.hostname,
            "ip_address": self._node_info.ip_address,
            "is_joined": self._joined,
            "heartbeat_interval": self._heartbeat_interval,
            "capabilities": self._node_info.capabilities,
        }

    @staticmethod
    def _get_local_ip() -> str:
        """Get the local IP address (best effort)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
