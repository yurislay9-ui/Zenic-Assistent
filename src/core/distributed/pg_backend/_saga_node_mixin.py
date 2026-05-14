"""
ZENIC-AGENTS - PostgreSQL Saga State, Circuit Breaker & Node Topology

Circuit breaker, saga state, and node topology methods for PgBackend.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.distributed.pg_backend")


# ============================================================
#  CIRCUIT BREAKER STATE MIXIN
# ============================================================

class PgCircuitMixin:
    """
    Mixin providing PostgreSQL circuit breaker state operations.

    Provides:
    - get_circuit_state()
    - update_circuit_state()
    """

    async def get_circuit_state(self, circuit_name: str) -> Optional[Dict[str, Any]]:
        try:
            rows = self._execute_query(
                """
                SELECT state_data, version, updated_at
                FROM coord_circuits
                WHERE circuit_name = %s
                """,
                (circuit_name,),
            )
            if not rows:
                return None
            row = rows[0]
            state = row["state_data"]
            if isinstance(state, str):
                state = json.loads(state)
            state["version"] = row["version"]
            state["updated_at"] = row["updated_at"]
            return state
        except Exception as exc:
            logger.error("PgBackend get_circuit_state error: %s", exc)
            return None

    async def update_circuit_state(
        self,
        circuit_name: str,
        state: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> bool:
        now = time.time()
        state_json = json.dumps({k: v for k, v in state.items() if k not in ("version", "updated_at")})

        try:
            if expected_version is not None:
                # Optimistic concurrency: only update if version matches
                affected = self._execute_modify(
                    """
                    UPDATE coord_circuits
                    SET state_data = %s,
                        version = version + 1,
                        updated_at = %s
                    WHERE circuit_name = %s AND version = %s
                    """,
                    (state_json, now, circuit_name, expected_version),
                )
            else:
                # Upsert: insert or replace
                affected = self._execute_modify(
                    """
                    INSERT INTO coord_circuits (circuit_name, state_data, version, updated_at)
                    VALUES (%s, %s, 1, %s)
                    ON CONFLICT (circuit_name) DO UPDATE
                    SET state_data = EXCLUDED.state_data,
                        version = coord_circuits.version + 1,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (circuit_name, state_json, now),
                )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend update_circuit_state error: %s", exc)
            return False


# ============================================================
#  SAGA STATE MIXIN
# ============================================================

class PgSagaMixin:
    """
    Mixin providing PostgreSQL saga state operations.

    Provides:
    - create_saga()
    - get_saga()
    - update_saga_step()
    - update_saga_status()
    """

    async def create_saga(
        self,
        saga_id: str,
        name: str,
        steps: List[Dict[str, Any]],
        initial_context: Dict[str, Any],
    ) -> bool:
        now = time.time()
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    # Insert saga
                    cur.execute(
                        """
                        INSERT INTO coord_sagas (saga_id, name, status, context_data, created_at, updated_at)
                        VALUES (%s, %s, 'PENDING', %s, %s, %s)
                        ON CONFLICT (saga_id) DO NOTHING
                        """,
                        (saga_id, name, json.dumps(initial_context), now, now),
                    )
                    if cur.rowcount == 0:
                        if not conn.autocommit:
                            conn.commit()
                        return False

                    # Insert steps
                    for i, step in enumerate(steps):
                        cur.execute(
                            """
                            INSERT INTO coord_saga_steps
                                (saga_id, step_name, step_order, status, timeout_seconds, updated_at)
                            VALUES (%s, %s, %s, 'PENDING', %s, %s)
                            """,
                            (
                                saga_id,
                                step.get("name", f"step-{i}"),
                                i,
                                step.get("timeout"),
                                now,
                            ),
                        )

                if not conn.autocommit:
                    conn.commit()
                return True
            except Exception:
                if not conn.autocommit:
                    conn.rollback()
                raise
            finally:
                self._put_conn(conn)
        except Exception as exc:
            logger.error("PgBackend create_saga error: %s", exc)
            return False

    async def get_saga(self, saga_id: str) -> Optional[Dict[str, Any]]:
        try:
            rows = self._execute_query(
                """
                SELECT saga_id, name, status, context_data, error,
                       created_at, updated_at
                FROM coord_sagas
                WHERE saga_id = %s
                """,
                (saga_id,),
            )
            if not rows:
                return None

            saga = rows[0]
            if isinstance(saga.get("context_data"), str):
                saga["context_data"] = json.loads(saga["context_data"])

            # Get steps
            steps = self._execute_query(
                """
                SELECT step_name, step_order, status, result, error,
                       timeout_seconds, updated_at
                FROM coord_saga_steps
                WHERE saga_id = %s
                ORDER BY step_order
                """,
                (saga_id,),
            )
            for step in steps:
                if isinstance(step.get("result"), str):
                    step["result"] = json.loads(step["result"])

            saga["steps"] = steps
            return saga
        except Exception as exc:
            logger.error("PgBackend get_saga error: %s", exc)
            return None

    async def update_saga_step(
        self,
        saga_id: str,
        step_name: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        now = time.time()
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_saga_steps
                SET status = %s,
                    result = %s,
                    error = %s,
                    updated_at = %s
                WHERE saga_id = %s AND step_name = %s
                """,
                (status, json.dumps(result) if result else None, error, now, saga_id, step_name),
            )
            # Also update saga's updated_at
            self._execute_modify(
                "UPDATE coord_sagas SET updated_at = %s WHERE saga_id = %s",
                (now, saga_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend update_saga_step error: %s", exc)
            return False

    async def update_saga_status(
        self,
        saga_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        now = time.time()
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_sagas
                SET status = %s, error = %s, updated_at = %s
                WHERE saga_id = %s
                """,
                (status, error, now, saga_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend update_saga_status error: %s", exc)
            return False


# ============================================================
#  NODE TOPOLOGY MIXIN
# ============================================================

class PgNodeMixin:
    """
    Mixin providing PostgreSQL node topology operations.

    Provides:
    - register_node()
    - heartbeat()
    - deregister_node()
    - list_nodes()
    """

    async def register_node(self, node_info: Dict[str, Any]) -> bool:
        now = time.time()
        node_id = node_info.get("node_id", "")
        try:
            self._execute_modify(
                """
                INSERT INTO coord_nodes
                    (node_id, hostname, ip_address, capabilities, status,
                     registered_at, last_heartbeat)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (node_id) DO UPDATE
                SET hostname = EXCLUDED.hostname,
                    ip_address = EXCLUDED.ip_address,
                    capabilities = EXCLUDED.capabilities,
                    last_heartbeat = EXCLUDED.last_heartbeat
                """,
                (
                    node_id,
                    node_info.get("hostname"),
                    node_info.get("ip_address"),
                    json.dumps(node_info.get("capabilities", {})),
                    json.dumps(node_info.get("status", {})),
                    now,
                    now,
                ),
            )
            return True
        except Exception as exc:
            logger.error("PgBackend register_node error: %s", exc)
            return False

    async def heartbeat(self, node_id: str, status: Optional[Dict[str, Any]] = None) -> bool:
        now = time.time()
        try:
            if status:
                affected = self._execute_modify(
                    """
                    UPDATE coord_nodes
                    SET last_heartbeat = %s, status = %s
                    WHERE node_id = %s
                    """,
                    (now, json.dumps(status), node_id),
                )
            else:
                affected = self._execute_modify(
                    "UPDATE coord_nodes SET last_heartbeat = %s WHERE node_id = %s",
                    (now, node_id),
                )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend heartbeat error: %s", exc)
            return False

    async def deregister_node(self, node_id: str) -> bool:
        try:
            affected = self._execute_modify(
                "DELETE FROM coord_nodes WHERE node_id = %s",
                (node_id,),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend deregister_node error: %s", exc)
            return False

    async def list_nodes(self, active_only: bool = True) -> List[Dict[str, Any]]:
        now = time.time()
        hb_cutoff = now - (self._config.heartbeat_interval * 3)
        try:
            if active_only:
                rows = self._execute_query(
                    """
                    SELECT node_id, hostname, ip_address, capabilities,
                           status, registered_at, last_heartbeat
                    FROM coord_nodes
                    WHERE last_heartbeat > %s
                    ORDER BY registered_at
                    """,
                    (hb_cutoff,),
                )
            else:
                rows = self._execute_query(
                    """
                    SELECT node_id, hostname, ip_address, capabilities,
                           status, registered_at, last_heartbeat
                    FROM coord_nodes
                    ORDER BY registered_at
                    """,
                )
            for row in rows:
                if isinstance(row.get("capabilities"), str):
                    row["capabilities"] = json.loads(row["capabilities"])
                if isinstance(row.get("status"), str):
                    row["status"] = json.loads(row["status"])
            return rows
        except Exception as exc:
            logger.error("PgBackend list_nodes error: %s", exc)
            return []
