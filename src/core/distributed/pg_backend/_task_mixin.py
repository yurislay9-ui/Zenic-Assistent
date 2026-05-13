"""
ZENIC-AGENTS - PostgreSQL Task Queue Operations

Task queue methods for PgBackend: enqueue, dequeue, complete,
fail, renew_lease, expire_leases.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.distributed.pg_backend")


# ============================================================
#  TASK QUEUE MIXIN
# ============================================================

class PgTaskMixin:
    """
    Mixin providing PostgreSQL task queue operations.

    Provides:
    - enqueue_task()
    - dequeue_task()
    - complete_task()
    - fail_task()
    - renew_lease()
    - expire_leases()
    """

    async def enqueue_task(
        self,
        queue_name: str,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        delay_until: Optional[float] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        try:
            self._execute_modify(
                """
                INSERT INTO coord_tasks
                    (task_id, queue_name, task_type, payload, priority,
                     delay_until, tenant_id, status, created_at, max_retries)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, 3)
                ON CONFLICT (task_id) DO NOTHING
                """,
                (
                    task_id, queue_name, task_type,
                    json.dumps(payload), priority,
                    delay_until, tenant_id, time.time(),
                ),
            )
            return True
        except Exception as exc:
            logger.error("PgBackend enqueue_task error: %s", exc)
            return False

    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        lease_seconds: float = 120.0,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        lease_expires = now + lease_seconds

        # Build dynamic WHERE clause
        conditions = [
            "t.queue_name = %s",
            "t.status = 'pending'",
            "(t.delay_until IS NULL OR t.delay_until <= %s)",
        ]
        params: list = [queue_name, now]

        if task_types:
            placeholders = ",".join(["%s"] * len(task_types))
            conditions.append(f"t.task_type IN ({placeholders})")
            params.extend(task_types)

        if tenant_id:
            conditions.append("t.tenant_id = %s")
            params.append(tenant_id)

        where_clause = " AND ".join(conditions)

        # Use FOR UPDATE SKIP LOCKED for atomic claim
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT t.*
                        FROM coord_tasks t
                        WHERE {where_clause}
                        ORDER BY t.priority DESC, t.created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """,
                        tuple(params),
                    )
                    row = cur.fetchone()

                    if row is None:
                        if not conn.autocommit:
                            conn.commit()
                        return None

                    columns = [desc[0] for desc in cur.description]
                    task = dict(zip(columns, row))
                    claimed_task_id = task["task_id"]

                    # Claim the task
                    cur.execute(
                        """
                        UPDATE coord_tasks
                        SET status = 'running',
                            worker_id = %s,
                            lease_expires_at = %s
                        WHERE task_id = %s
                        """,
                        (worker_id, lease_expires, claimed_task_id),
                    )

                if not conn.autocommit:
                    conn.commit()

                # Parse JSONB payload
                if isinstance(task.get("payload"), str):
                    task["payload"] = json.loads(task["payload"])
                return task

            except Exception:
                if not conn.autocommit:
                    conn.rollback()
                raise
            finally:
                self._put_conn(conn)

        except Exception as exc:
            logger.error("PgBackend dequeue_task error: %s", exc)
            return None

    async def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_tasks
                SET status = 'completed',
                    completed_at = %s,
                    result = %s,
                    lease_expires_at = NULL
                WHERE task_id = %s
                """,
                (time.time(), json.dumps(result) if result else None, task_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend complete_task error: %s", exc)
            return False

    async def fail_task(self, task_id: str, error: str, retryable: bool = True) -> bool:
        try:
            if retryable:
                # Reset to pending and increment retry_count
                affected = self._execute_modify(
                    """
                    UPDATE coord_tasks
                    SET status = CASE
                            WHEN retry_count < max_retries THEN 'pending'
                            ELSE 'failed'
                        END,
                        retry_count = retry_count + 1,
                        error = %s,
                        worker_id = CASE
                            WHEN retry_count < max_retries THEN NULL
                            ELSE worker_id
                        END,
                        lease_expires_at = CASE
                            WHEN retry_count < max_retries THEN NULL
                            ELSE lease_expires_at
                        END,
                        completed_at = CASE
                            WHEN retry_count >= max_retries THEN %s
                            ELSE completed_at
                        END
                    WHERE task_id = %s
                    """,
                    (error, time.time(), task_id),
                )
            else:
                affected = self._execute_modify(
                    """
                    UPDATE coord_tasks
                    SET status = 'failed',
                        error = %s,
                        completed_at = %s,
                        lease_expires_at = NULL
                    WHERE task_id = %s
                    """,
                    (error, time.time(), task_id),
                )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend fail_task error: %s", exc)
            return False

    async def renew_lease(self, task_id: str, additional_seconds: float = 60.0) -> bool:
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_tasks
                SET lease_expires_at = %s
                WHERE task_id = %s AND status = 'running'
                """,
                (time.time() + additional_seconds, task_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend renew_lease error: %s", exc)
            return False

    async def expire_leases(self, queue_name: str) -> int:
        now = time.time()
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_tasks
                SET status = 'pending',
                    worker_id = NULL,
                    lease_expires_at = NULL
                WHERE queue_name = %s
                  AND status = 'running'
                  AND lease_expires_at < %s
                """,
                (queue_name, now),
            )
            if affected > 0:
                logger.info(
                    "PgBackend: Expired %d leases in queue '%s'",
                    affected, queue_name,
                )
            return affected
        except Exception as exc:
            logger.error("PgBackend expire_leases error: %s", exc)
            return 0
