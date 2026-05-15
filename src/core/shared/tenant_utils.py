"""
ZENIC-AGENTS — Shared Tenant Utility Functions.

Eliminates duplicated tenant ID resolution code across engine modules.
GraphASTEngine, MerkleLedger, and TheoremCache all had identical
try/except blocks to resolve tenant_id from TenantContext.

NOTE: The tenant module (src.core.tenant) has been removed.
All operations now use the anonymous tenant ID as fallback.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = ["ANONYMOUS_TENANT", "resolve_tenant_id"]

# Default tenant_id for backward compatibility
# Import this constant instead of hardcoding "__anonymous__" elsewhere.
ANONYMOUS_TENANT = "__anonymous__"


def resolve_tenant_id() -> str:
    """Resolve the current tenant ID.

    NOTE: The tenant module (src.core.tenant) has been removed.
    Always returns the anonymous tenant ID.

    Returns:
        The anonymous tenant ID string.
    """
    # Tenant module removed — always use anonymous
    return ANONYMOUS_TENANT
