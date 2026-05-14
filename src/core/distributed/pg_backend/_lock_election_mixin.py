"""
ZENIC-AGENTS - PostgreSQL Distributed Locks & Leader Election

Lock and election methods for PgBackend: acquire_lock, release_lock,
extend_lock, is_locked, campaign, abdicate, get_leader, renew_leadership.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger("zenic_agents.distributed.pg_backend")


# ============================================================
#  LOCK & ELECTION MIXIN
# ============================================================

class PgLockElectionMixin:
    """
    Mixin providing PostgreSQL distributed lock and leader election operations.

    Provides:
    - acquire_lock() / release_lock() / extend_lock() / is_locked()
    - campaign() / abdicate() / get_leader() / renew_leadership()
    """

    async def acquire_lock(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float = 60.0,
        timeout_seconds: float = 0.0,
    ) -> bool:
        deadline = time.time() + timeout_seconds

        while True:
            now = time.time()
            try:
                # Try to insert or update expired lock
                affected = self._execute_modify(
                    """
                    INSERT INTO coord_locks (lock_name, holder_id, expires_at, acquired_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (lock_name) DO UPDATE
                    SET holder_id = EXCLUDED.holder_id,
                        expires_at = EXCLUDED.expires_at,
                        acquired_at = EXCLUDED.acquired_at
                    WHERE coord_locks.expires_at < %s
                       OR coord_locks.holder_id = %s
                    """,
                    (lock_name, holder_id, now + ttl_seconds, now, now, holder_id),
                )
                if affected > 0:
                    return True
            except Exception as exc:
                logger.error("PgBackend acquire_lock error: %s", exc)
                return False

            if time.time() >= deadline:
                return False

            time.sleep(min(0.1, max(0, deadline - time.time())))

    async def release_lock(self, lock_name: str, holder_id: str) -> bool:
        try:
            affected = self._execute_modify(
                """
                DELETE FROM coord_locks
                WHERE lock_name = %s AND holder_id = %s
                """,
                (lock_name, holder_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend release_lock error: %s", exc)
            return False

    async def extend_lock(self, lock_name: str, holder_id: str, additional_seconds: float = 30.0) -> bool:
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_locks
                SET expires_at = %s
                WHERE lock_name = %s AND holder_id = %s
                """,
                (time.time() + additional_seconds, lock_name, holder_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend extend_lock error: %s", exc)
            return False

    async def is_locked(self, lock_name: str) -> bool:
        try:
            rows = self._execute_query(
                """
                SELECT 1 AS locked
                FROM coord_locks
                WHERE lock_name = %s AND expires_at > %s
                LIMIT 1
                """,
                (lock_name, time.time()),
            )
            return len(rows) > 0
        except Exception as exc:
            logger.error("PgBackend is_locked error: %s", exc)
            return False

    # ----------------------------------------------------------
    #  LEADER ELECTION
    # ----------------------------------------------------------

    async def campaign(self, election_name: str, candidate_id: str, ttl_seconds: float = 30.0) -> bool:
        now = time.time()
        try:
            affected = self._execute_modify(
                """
                INSERT INTO coord_elections (election_name, leader_id, expires_at, acquired_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (election_name) DO UPDATE
                SET leader_id = EXCLUDED.leader_id,
                    expires_at = EXCLUDED.expires_at,
                    acquired_at = EXCLUDED.acquired_at
                WHERE coord_elections.expires_at < %s
                   OR coord_elections.leader_id = %s
                """,
                (election_name, candidate_id, now + ttl_seconds, now, now, candidate_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend campaign error: %s", exc)
            return False

    async def abdicate(self, election_name: str, leader_id: str) -> bool:
        try:
            affected = self._execute_modify(
                """
                DELETE FROM coord_elections
                WHERE election_name = %s AND leader_id = %s
                """,
                (election_name, leader_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend abdicate error: %s", exc)
            return False

    async def get_leader(self, election_name: str) -> Optional[str]:
        try:
            rows = self._execute_query(
                """
                SELECT leader_id FROM coord_elections
                WHERE election_name = %s AND expires_at > %s
                LIMIT 1
                """,
                (election_name, time.time()),
            )
            return rows[0]["leader_id"] if rows else None
        except Exception as exc:
            logger.error("PgBackend get_leader error: %s", exc)
            return None

    async def renew_leadership(self, election_name: str, leader_id: str, ttl_seconds: float = 30.0) -> bool:
        try:
            affected = self._execute_modify(
                """
                UPDATE coord_elections
                SET expires_at = %s
                WHERE election_name = %s AND leader_id = %s
                """,
                (time.time() + ttl_seconds, election_name, leader_id),
            )
            return affected > 0
        except Exception as exc:
            logger.error("PgBackend renew_leadership error: %s", exc)
            return False
