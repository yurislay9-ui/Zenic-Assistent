"""
SmartMemory — Tenant Management Mixin.

Tenant isolation, multi-client management, and usage tracking.
"""

import logging
import os
import sqlite3
from typing import Dict, List, Optional

from ..types import DB_PATH
# Tenant module removed — use fallback from parent module
# from src.core.tenant._context import get_current_tenant, set_current_tenant, TenantContext
# These are provided by _core.py via the fallback context
try:
    from src.core.tenant._context import get_current_tenant, set_current_tenant, TenantContext
except ImportError:
    from src.core.shared.tenant_utils import ANONYMOUS_TENANT

    class TenantContext:
        """Minimal fallback for removed TenantContext."""
        def __init__(self, tenant_id=ANONYMOUS_TENANT, user_id=0, username="",
                     role="viewer", plan="free", quotas=None, features=None,
                     permissions=None, auth_method="", is_authenticated=False, extra=None):
            self.tenant_id = tenant_id
            self.effective_tenant_id = tenant_id
            self.user_id = user_id
            self.username = username
            self.role = role
            self.plan = plan
            self.quotas = quotas or {}
            self.features = features or []
            self.permissions = permissions or []
            self.auth_method = auth_method
            self.is_authenticated = is_authenticated
            self.extra = extra or {}

    def get_current_tenant():
        return TenantContext()

    def set_current_tenant(ctx):
        pass

logger = logging.getLogger(__name__)


class TenantMixin:
    """Mixin providing tenant and multi-client management for SmartMemory."""

    def set_tenant_id(self, tenant_id: str) -> None:
        """Phase 2: Set the tenant_id for all subsequent operations.

        Updates both the instance variable and the thread-local
        TenantContext so that deeply-nested code also sees the
        correct tenant.

        Args:
            tenant_id: The tenant identifier to scope operations to.
                       Must be a non-empty string.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        self._tenant_id = tenant_id.strip()

        # Also update the thread-local context so nested code sees the change
        current_ctx = get_current_tenant()
        if current_ctx.tenant_id != self._tenant_id:
            new_ctx = TenantContext(
                tenant_id=self._tenant_id,
                user_id=current_ctx.user_id,
                username=current_ctx.username,
                role=current_ctx.role,
                plan=current_ctx.plan,
                quotas=current_ctx.quotas,
                features=current_ctx.features,
                permissions=current_ctx.permissions,
                auth_method=current_ctx.auth_method,
                is_authenticated=current_ctx.is_authenticated,
                extra=current_ctx.extra,
            )
            set_current_tenant(new_ctx)

        logger.info(f"SmartMemory: tenant_id set to '{self._tenant_id}'")

    def list_clients(self, tenant_id: Optional[str] = None) -> List[str]:
        """Returns distinct client_ids, optionally scoped by tenant_id.

        Args:
            tenant_id: If provided, list clients only for this tenant.
                       Defaults to the current instance tenant_id.
        """
        tid = tenant_id or self._tenant_id
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT DISTINCT client_id FROM semantic_cache WHERE tenant_id=?",
                (tid,)
            ).fetchall()
        return [r[0] for r in rows]

    def clear_client_data(self, client_id: str, tenant_id: Optional[str] = None):
        """Deletes all data for a specific client, scoped by tenant_id.

        Args:
            client_id: The client identifier to clear data for.
            tenant_id: If provided, scope to this tenant. Defaults to
                       the current instance tenant_id.
        """
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("client_id must be a non-empty string")
        tid = tenant_id or self._tenant_id
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        with sqlite3.connect(DB_PATH) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                conn.execute(
                    f'DELETE FROM "{table}" WHERE client_id=? AND tenant_id=?',
                    (client_id, tid)
                )
        # Also remove from working memory (thread-safe)
        with self._working_lock:
            self._working_memory = [
                e for e in self._working_memory
                if not (e.client_id == client_id and e.tenant_id == tid)
            ]
        logger.info(
            f"SmartMemory: Cleared all data for client_id='{client_id}', "
            f"tenant_id='{tid}'"
        )

    def purge_tenant_data(self, tenant_id: str) -> int:
        """Delete ALL data for a tenant across all tables.

        Used for GDPR compliance (right to be forgotten) or tenant
        deprovisioning. This is a destructive operation.

        Args:
            tenant_id: The tenant identifier to purge all data for.

        Returns:
            Total number of rows deleted across all tables.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        tid = tenant_id.strip()
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        total_deleted = 0
        with sqlite3.connect(DB_PATH) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                cursor = conn.execute(
                    f'DELETE FROM "{table}" WHERE tenant_id=?',
                    (tid,)
                )
                total_deleted += cursor.rowcount
        # Also remove from working memory (thread-safe)
        with self._working_lock:
            self._working_memory = [
                e for e in self._working_memory if e.tenant_id != tid
            ]
        logger.info(
            f"SmartMemory: Purged all data for tenant_id='{tid}' "
            f"({total_deleted} rows deleted)"
        )
        return total_deleted

    def get_tenant_usage_mb(self, tenant_id: str) -> float:
        """Calculate approximate storage usage in MB for a tenant.

        Estimates the storage consumed by all rows belonging to the
        given tenant across all tables. Uses row count and average
        row size estimation.

        Args:
            tenant_id: The tenant identifier to measure usage for.

        Returns:
            Estimated storage usage in megabytes.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        tid = tenant_id.strip()

        total_bytes = 0
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]

        with sqlite3.connect(DB_PATH) as conn:
            db_size_bytes = 0
            try:
                db_size_bytes = os.path.getsize(DB_PATH)
            except OSError:
                pass

            total_tenant_rows = 0
            total_all_rows = 0
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                try:
                    tenant_count = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE tenant_id=?',
                        (tid,)
                    ).fetchone()[0]
                    total_tenant_rows += tenant_count

                    all_count = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                    total_all_rows += all_count
                except sqlite3.OperationalError:
                    pass

            if total_all_rows > 0 and db_size_bytes > 0:
                total_bytes = (total_tenant_rows / total_all_rows) * db_size_bytes

        usage_mb = total_bytes / (1024 * 1024)
        logger.debug(
            f"SmartMemory: Tenant '{tid}' usage: {usage_mb:.2f}MB "
            f"({total_tenant_rows} rows)"
        )
        return usage_mb
