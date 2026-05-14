"""TenantMixin deprovision method: GDPR right-to-be-forgotten flow."""

from ._plans import PLAN_DEFINITIONS
from .._imports import (
    logger, sqlite3, json, threading,
    datetime, timezone,
)
from typing import Dict, Any


class TenantDeprovisionMixin:
    """Hard-delete tenant and ALL associated data (GDPR compliance)."""

    def deprovision_tenant(self, tenant_id: str) -> Dict[str, Any]:
        """Hard-delete a tenant and ALL associated data across all databases.

        This is the GDPR 'right to be forgotten' / full deprovisioning flow.
        It purges data from: SmartMemory, MerkleLedger, TheoremCache,
        GraphAST, RequestLog, auth DB (users unassigned, tenant deactivated).

        Args:
            tenant_id: Tenant identifier to deprovision.

        Returns:
            Dict with purge summary on success, or {'error': ...} on failure.
        """
        try:
            from src.core.patterns.resilience.retry import RetryConfig, with_retry
            _HAS_RETRY = True
        except ImportError:
            _HAS_RETRY = False
            RetryConfig = None
            with_retry = None

        # Validate tenant exists
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}

        purge_summary: Dict[str, int] = {}
        total_purged = 0

        # 1. Deactivate tenant first (prevents new data while purging)
        self.deactivate_tenant(tenant_id)

        # 2. Unassign all users from this tenant
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute(
                    "UPDATE users SET tenant_id = NULL, updated_at = ? WHERE tenant_id = ?",
                    (datetime.now(timezone.utc).isoformat(), tenant_id),
                )
                c.commit()
                purge_summary["users_unassigned"] = cur.rowcount
        except sqlite3.Error as e:
            logger.error("Deprovision: unassign users error: %s", e)

        # 3. Delete tenant_usage rows
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute(
                    "DELETE FROM tenant_usage WHERE tenant_id = ?", (tenant_id,)
                )
                c.commit()
                purge_summary["tenant_usage_deleted"] = cur.rowcount
        except sqlite3.Error as e:
            logger.error("Deprovision: tenant_usage delete error: %s", e)

        # 4. Purge data from all tenant-aware databases (with retry)
        if _HAS_RETRY:
            _purge_retry = RetryConfig(
                max_attempts=3, base_delay=0.5, max_delay=5.0,
                backoff_strategy="exponential", jitter=True,
                retryable_exceptions=(Exception,),
            )

        # SmartMemory purge
        try:
            from src.core.smart_memory import SmartMemory
            sm = SmartMemory()
            if _HAS_RETRY:
                count = with_retry(sm.purge_tenant_data, _purge_retry, tenant_id)
            else:
                count = sm.purge_tenant_data(tenant_id)
            purge_summary["smart_memory_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: SmartMemory purge failed: %s", e)
            purge_summary["smart_memory_purged"] = -1

        # MerkleLedger purge
        try:
            from src.core.level7_merkle_ledger.ledger import MerkleLedger
            ml = MerkleLedger()
            if _HAS_RETRY:
                count = with_retry(ml.purge_tenant_ledger, _purge_retry, tenant_id)
            else:
                count = ml.purge_tenant_ledger(tenant_id)
            purge_summary["merkle_ledger_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: MerkleLedger purge failed: %s", e)
            purge_summary["merkle_ledger_purged"] = -1

        # TheoremCache purge
        try:
            from src.core.level8_theorem_cache.cache import TheoremCache
            tc = TheoremCache()
            if _HAS_RETRY:
                count = with_retry(tc.purge_tenant_cache, _purge_retry, tenant_id)
            else:
                count = tc.purge_tenant_cache(tenant_id)
            purge_summary["theorem_cache_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: TheoremCache purge failed: %s", e)
            purge_summary["theorem_cache_purged"] = -1

        # GraphAST purge
        try:
            from src.core.level3_graph_ast.engine import GraphASTEngine
            gae = GraphASTEngine()
            if _HAS_RETRY:
                count = with_retry(gae.purge_tenant_data, _purge_retry, tenant_id)
            else:
                count = gae.purge_tenant_data(tenant_id)
            purge_summary["graph_ast_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: GraphAST purge failed: %s", e)
            purge_summary["graph_ast_purged"] = -1

        # RequestLog purge
        try:
            from src.core.shared.db_initializer import get_connection
            conn = get_connection("request_log.sqlite")
            cursor = conn.execute("DELETE FROM requests WHERE tenant_id = ?", (tenant_id,))
            conn.commit()
            purge_summary["request_log_purged"] = cursor.rowcount
            total_purged += cursor.rowcount
        except Exception as e:
            logger.warning("Deprovision: RequestLog purge failed: %s", e)
            purge_summary["request_log_purged"] = -1

        # 5. Delete tenant row from auth DB
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
                c.commit()
                purge_summary["tenant_deleted"] = cur.rowcount
        except sqlite3.Error as e:
            logger.error("Deprovision: tenant delete error: %s", e)

        purge_summary["total_purged"] = total_purged
        purge_summary["tenant_id"] = tenant_id
        purge_summary["tenant_name"] = tenant.get("name", "")
        logger.info(
            "Deprovision complete for tenant '%s' (%s): %d total rows purged",
            tenant_id, tenant.get("name", ""), total_purged,
        )
        return purge_summary
