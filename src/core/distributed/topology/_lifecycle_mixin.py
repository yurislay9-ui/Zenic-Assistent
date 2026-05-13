"""
ZENIC-AGENTS - Cluster Topology: Lifecycle Mixin

Join, leave, and heartbeat methods for ClusterTopology.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from ._types import NodeInfo, NodeState

logger = logging.getLogger(__name__)


class LifecycleMixin:
    """Mixin providing join/leave/heartbeat for ClusterTopology."""

    async def join(self: Any) -> bool:
        """
        Register this node in the cluster.

        Returns:
            True if registration succeeded.
        """
        self._node_info.state = NodeState.ACTIVE
        success = await self._backend.register_node(
            self._node_info.to_dict()
        )

        if success:
            self._joined = True
            logger.info(
                "ClusterTopology: Node %s joined cluster "
                "(hostname=%s, ip=%s)",
                self._node_info.node_id,
                self._node_info.hostname,
                self._node_info.ip_address,
            )

        return success

    async def leave(self: Any) -> bool:
        """
        Deregister this node from the cluster.

        Returns:
            True if deregistration succeeded.
        """
        self.stop_heartbeat()

        success = await self._backend.deregister_node(
            self._node_info.node_id
        )

        if success:
            self._joined = False
            logger.info(
                "ClusterTopology: Node %s left cluster",
                self._node_info.node_id,
            )

        return success

    async def send_heartbeat(self: Any, status: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send a heartbeat for this node.

        Args:
            status: Optional status payload (load, queue depth, etc.).

        Returns:
            True if the heartbeat was recorded.
        """
        return await self._backend.heartbeat(
            self._node_info.node_id, status,
        )

    def start_heartbeat(self: Any) -> None:
        """Start the background heartbeat thread."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"topology-heartbeat-{self._node_info.node_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()
        logger.debug(
            "ClusterTopology: Heartbeat started for %s "
            "(interval=%.1fs)",
            self._node_info.node_id, self._heartbeat_interval,
        )

    def stop_heartbeat(self: Any) -> None:
        """Stop the background heartbeat thread."""
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5.0)

    def _heartbeat_loop(self: Any) -> None:
        """Background loop that sends periodic heartbeats."""
        while not self._stop_event.is_set():
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        self.send_heartbeat({
                            "state": self._node_info.state.value,
                        })
                    )
                finally:
                    loop.close()
            except Exception as exc:
                logger.debug(
                    "ClusterTopology: Heartbeat error for %s: %s",
                    self._node_info.node_id, exc,
                )

            self._stop_event.wait(timeout=self._heartbeat_interval)
