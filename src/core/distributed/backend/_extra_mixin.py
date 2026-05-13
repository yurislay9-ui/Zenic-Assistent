"""CoordinationBackend - Additional methods."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.distributed.backend")


class CoordinationBackendExtraMixin:
    """Additional methods."""

    async def extend_lock(self, lock_name: str, holder_id: str, additional_seconds: float = 30.0) -> bool:
        """
        Extend a held lock's TTL.

        Args:
            lock_name: Name of the lock.
            holder_id: Must match the current holder.
            additional_seconds: Extra time to add.

        Returns:
            True if the lock was extended.
        """
    async def is_locked(self, lock_name: str) -> bool:
        """
        Check if a lock is currently held.

        Args:
            lock_name: Name of the lock.

        Returns:
            True if the lock is currently held by someone.
        """
    async def campaign(self, election_name: str, candidate_id: str, ttl_seconds: float = 30.0) -> bool:
        """
        Attempt to become leader for the given election.

        Args:
            election_name: Name of the leadership position.
            candidate_id: ID of the candidate (usually node_id).
            ttl_seconds: Leadership duration before re-campaign needed.

        Returns:
            True if leadership was acquired.
        """
    async def abdicate(self, election_name: str, leader_id: str) -> bool:
        """
        Voluntarily step down as leader.

        Args:
            election_name: Name of the leadership position.
            leader_id: Must match the current leader.

        Returns:
            True if leadership was relinquished.
        """
    async def get_leader(self, election_name: str) -> Optional[str]:
        """
        Get the current leader for an election.

        Args:
            election_name: Name of the leadership position.

        Returns:
            Leader ID, or None if no leader.
        """
    async def renew_leadership(self, election_name: str, leader_id: str, ttl_seconds: float = 30.0) -> bool:
        """
        Renew leadership before it expires.

        Args:
            election_name: Name of the leadership position.
            leader_id: Must match the current leader.
            ttl_seconds: New TTL from now.

        Returns:
            True if leadership was renewed.
        """
    async def get_circuit_state(self, circuit_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the shared state of a circuit breaker.

        Args:
            circuit_name: Name of the circuit breaker.

        Returns:
            Dict with circuit state, or None if not found.
        """
    async def update_circuit_state(
        self,
        circuit_name: str,
        state: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> bool:
        """
        Update circuit breaker state with optimistic concurrency.

        Args:
            circuit_name: Name of the circuit breaker.
            state: New state to write.
            expected_version: If set, update only if current version matches.

        Returns:
            True if the update succeeded (version matched if specified).
        """
    async def create_saga(
        self,
        saga_id: str,
        name: str,
        steps: List[Dict[str, Any]],
        initial_context: Dict[str, Any],
    ) -> bool:
        """
        Persist a new saga with its steps and initial context.

        Args:
            saga_id: Unique saga identifier.
            name: Human-readable saga name.
            steps: List of step definitions (each with name, action_type,
                   compensation_type, timeout).
            initial_context: Initial context data.

        Returns:
            True if the saga was created.
        """
    async def get_saga(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """
        Get saga state by ID.

        Args:
            saga_id: Unique saga identifier.

        Returns:
            Dict with saga state, or None if not found.
        """
    async def update_saga_step(
        self,
        saga_id: str,
        step_name: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a specific saga step.

        Args:
            saga_id: Unique saga identifier.
            step_name: Step to update.
            status: New step status (PENDING/RUNNING/COMPLETED/COMPENSATING/COMPENSATED/FAILED).
            result: Optional step result payload.
            error: Optional error message.

        Returns:
            True if the step was updated.
        """
    async def update_saga_status(
        self,
        saga_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update the overall saga status.

        Args:
            saga_id: Unique saga identifier.
            status: New saga status.
            error: Optional error message.

        Returns:
            True if the saga was updated.
        """
    async def register_node(self, node_info: Dict[str, Any]) -> bool:
        """
        Register this node in the cluster topology.

        Args:
            node_info: Node registration data (id, hostname, capabilities, etc.).

        Returns:
            True if registration succeeded.
        """
    async def heartbeat(self, node_id: str, status: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send a heartbeat for this node.

        Args:
            node_id: Node ID sending the heartbeat.
            status: Optional current status data (load, queue depth, etc.).

        Returns:
            True if the heartbeat was recorded.
        """
    async def deregister_node(self, node_id: str) -> bool:
        """
        Remove a node from the cluster topology.

        Args:
            node_id: Node to remove.

        Returns:
            True if the node was found and removed.
        """
    async def list_nodes(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        List nodes in the cluster.

        Args:
            active_only: If True, only return nodes with recent heartbeats.

        Returns:
            List of node info dicts.
        """
