"""
Tenant management mixin for AuthService.

Provides multi-tenant support: tenant CRUD, user-tenant assignment,
per-tenant quotas, and tenant-aware configuration.

Phase 1 SaaS Fundamentals — adds tenants table, tenant-aware users,
and plan-based resource quotas.
"""

from ._plans import PLAN_DEFINITIONS
from ._crud_mixin import TenantCrudMixin
from ._deprovision_mixin import TenantDeprovisionMixin
from ._usage_mixin import TenantUsageMixin

__all__ = ["TenantMixin", "PLAN_DEFINITIONS"]


class TenantMixin(TenantCrudMixin, TenantUsageMixin, TenantDeprovisionMixin):
    """Tenant management for AuthService.

    Requires ``_conn()``, ``_lock``, and ``init_db()`` from other mixins.
    Call ``init_tenant_tables()`` from ``init_db()`` to create the schema.
    """
