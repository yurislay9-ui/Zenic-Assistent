"""
ZENIC-AGENTS — Shared Tenant Utility Functions.

Eliminates duplicated tenant ID resolution code across engine modules.
GraphASTEngine, MerkleLedger, and TheoremCache all had identical
try/except blocks to resolve tenant_id from TenantContext.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = ["ANONYMOUS_TENANT", "resolve_tenant_id"]

# Default tenant_id for backward compatibility
# Import this constant instead of hardcoding "__anonymous__" elsewhere.
ANONYMOUS_TENANT = "__anonymous__"


def resolve_tenant_id() -> str:
    """Resolve the current tenant ID from thread-local TenantContext.

    Tries to import and call get_current_tenant() from the tenant module.
    If the tenant context is not available (e.g., running outside a
    request context, or the tenant module is not installed), returns
    the anonymous tenant ID.

    Returns:
        The effective tenant ID string, or ANONYMOUS_TENANT as fallback.
    """
    try:
        from src.core.tenant._context import get_current_tenant
        return get_current_tenant().effective_tenant_id
    except Exception:
        return ANONYMOUS_TENANT
