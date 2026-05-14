"""
ZENIC-AGENTS - Cluster Topology: Types and Data Contracts

NodeState enum and NodeInfo dataclass for cluster topology management.
"""

import enum
import logging
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict

logger = logging.getLogger(__name__)


class NodeState(str, enum.Enum):
    """Node states."""
    JOINING = "joining"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    LEAVING = "leaving"
    DEAD = "dead"


@dataclass
class NodeInfo:
    """
    Information about a node in the cluster.

    Attributes:
        node_id: Unique node identifier.
        hostname: Machine hostname.
        ip_address: Node IP address.
        capabilities: Dict of node capabilities (task types, resources).
        state: Current node state.
        registered_at: Timestamp of registration.
        last_heartbeat: Timestamp of last heartbeat.
        status: Current status payload (load, queue depth, etc.).
    """
    node_id: str = ""
    hostname: str = ""
    ip_address: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)
    state: NodeState = NodeState.JOINING
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    status: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"node-{uuid.uuid4().hex[:8]}"
        if not self.hostname:
            self.hostname = socket.gethostname()
        if self.registered_at == 0.0:
            self.registered_at = time.time()
        if self.last_heartbeat == 0.0:
            self.last_heartbeat = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for backend storage."""
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "capabilities": self.capabilities,
            "state": self.state.value,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeInfo":
        """Deserialize from backend dict."""
        state_str = data.get("state", "joining")
        try:
            state = NodeState(state_str)
        except ValueError:
            state = NodeState.JOINING

        return cls(
            node_id=data.get("node_id", ""),
            hostname=data.get("hostname", ""),
            ip_address=data.get("ip_address", ""),
            capabilities=data.get("capabilities", {}),
            state=state,
            registered_at=data.get("registered_at", 0.0),
            last_heartbeat=data.get("last_heartbeat", 0.0),
            status=data.get("status", {}),
        )
