"""
Memory Backend — Coordination Operations Mixin.

Contains leader election, circuit breaker state, saga state,
and node topology operations for MemoryBackend.
"""

import copy
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CoordinationMixin:
    """Mixin providing coordination operations for MemoryBackend."""

    # ----------------------------------------------------------
    #  LEADER ELECTION
    # ----------------------------------------------------------

    async def campaign(self, election_name: str, candidate_id: str, ttl_seconds: float = 30.0) -> bool:
        with self._lock:
            election = self._elections.get(election_name)
            now = time.time()

            if election is None or election["expires_at"] < now:
                self._elections[election_name] = {
                    "leader_id": candidate_id,
                    "expires_at": now + ttl_seconds,
                    "acquired_at": now,
                }
                return True

            if election["leader_id"] == candidate_id:
                election["expires_at"] = now + ttl_seconds
                return True

            return False

    async def abdicate(self, election_name: str, leader_id: str) -> bool:
        with self._lock:
            election = self._elections.get(election_name)
            if election is None or election["leader_id"] != leader_id:
                return False
            del self._elections[election_name]
            return True

    async def get_leader(self, election_name: str) -> Optional[str]:
        with self._lock:
            election = self._elections.get(election_name)
            if election is None:
                return None
            if election["expires_at"] < time.time():
                del self._elections[election_name]
                return None
            return election["leader_id"]

    async def renew_leadership(self, election_name: str, leader_id: str, ttl_seconds: float = 30.0) -> bool:
        with self._lock:
            election = self._elections.get(election_name)
            if election is None or election["leader_id"] != leader_id:
                return False
            election["expires_at"] = time.time() + ttl_seconds
            return True

    # ----------------------------------------------------------
    #  CIRCUIT BREAKER STATE
    # ----------------------------------------------------------

    async def get_circuit_state(self, circuit_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._circuits.get(circuit_name))

    async def update_circuit_state(
        self,
        circuit_name: str,
        state: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> bool:
        with self._lock:
            current = self._circuits.get(circuit_name)
            if current is not None and expected_version is not None:
                if current.get("version", 0) != expected_version:
                    return False
            state_copy = copy.deepcopy(state)
            state_copy["version"] = (current.get("version", 0) + 1) if current else 1
            state_copy["updated_at"] = time.time()
            self._circuits[circuit_name] = state_copy
            return True

    # ----------------------------------------------------------
    #  SAGA STATE
    # ----------------------------------------------------------

    async def create_saga(
        self,
        saga_id: str,
        name: str,
        steps: List[Dict[str, Any]],
        initial_context: Dict[str, Any],
    ) -> bool:
        with self._lock:
            if saga_id in self._sagas:
                return False
            self._sagas[saga_id] = {
                "saga_id": saga_id,
                "name": name,
                "status": "PENDING",
                "steps": steps,
                "context": copy.deepcopy(initial_context),
                "created_at": time.time(),
                "updated_at": time.time(),
                "error": None,
            }
            return True

    async def get_saga(self, saga_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            saga = self._sagas.get(saga_id)
            return copy.deepcopy(saga) if saga else None

    async def update_saga_step(
        self,
        saga_id: str,
        step_name: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            saga = self._sagas.get(saga_id)
            if saga is None:
                return False
            for step in saga["steps"]:
                if step["name"] == step_name:
                    step["status"] = status
                    step["result"] = result
                    step["error"] = error
                    step["updated_at"] = time.time()
                    break
            saga["updated_at"] = time.time()
            return True

    async def update_saga_status(
        self,
        saga_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            saga = self._sagas.get(saga_id)
            if saga is None:
                return False
            saga["status"] = status
            saga["error"] = error
            saga["updated_at"] = time.time()
            return True

    # ----------------------------------------------------------
    #  NODE TOPOLOGY
    # ----------------------------------------------------------

    async def register_node(self, node_info: Dict[str, Any]) -> bool:
        with self._lock:
            node_id = node_info.get("node_id", "")
            self._nodes[node_id] = {
                **copy.deepcopy(node_info),
                "registered_at": time.time(),
                "last_heartbeat": time.time(),
            }
            return True

    async def heartbeat(self, node_id: str, status: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node["last_heartbeat"] = time.time()
            if status:
                node["status"] = copy.deepcopy(status)
            return True

    async def deregister_node(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                return True
            return False

    async def list_nodes(self, active_only: bool = True) -> List[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            result = []
            for node in self._nodes.values():
                if active_only:
                    hb_interval = self._config.heartbeat_interval
                    if now - node.get("last_heartbeat", 0) > hb_interval * 3:
                        continue
                result.append(copy.deepcopy(node))
            return result
