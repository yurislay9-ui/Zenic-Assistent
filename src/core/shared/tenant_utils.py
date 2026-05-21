"""
ZENIC-AGENTS — Shared Tenant Utility Functions.

Multi-tenant context resolution with fail-closed security.
When no tenant is explicitly set, the system denies access rather
than falling back to a shared anonymous namespace.

INVARIANT: resolve_tenant_id() NEVER returns __anonymous__ in production.
           In dev mode (ZENIC_DEV_MODE=1), __anonymous__ is allowed with a warning.

Migration from v2:
  - resolve_tenant_id() still returns a string (backward compatible)
  - In production without ZENIC_DEV_MODE, raises RuntimeError if no tenant set
  - Set ZENIC_DEV_MODE=1 to preserve old behavior (anonymous fallback)
"""

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ANONYMOUS_TENANT",
    "resolve_tenant_id",
    "set_tenant_context",
    "clear_tenant_context",
    "require_tenant",
]

# Default tenant_id for backward compatibility
# Import this constant instead of hardcoding "__anonymous__" elsewhere.
ANONYMOUS_TENANT = "__anonymous__"

# ── Thread-local tenant context ──────────────────────────
_tenant_context = threading.local()


def set_tenant_context(tenant_id: str) -> None:
    """Set the current thread's tenant ID.

    Args:
        tenant_id: The tenant identifier. Must not be empty or ANONYMOUS_TENANT
                   unless in dev mode.

    Raises:
        ValueError: If tenant_id is empty or anonymous in production.
    """
    if not tenant_id or tenant_id.strip() == "":
        raise ValueError("tenant_id cannot be empty")
    if tenant_id == ANONYMOUS_TENANT:
        if os.environ.get("ZENIC_DEV_MODE") != "1":
            raise ValueError(
                f"Cannot set tenant to {ANONYMOUS_TENANT!r} in production. "
                "Set ZENIC_DEV_MODE=1 for development."
            )
        logger.warning("Tenant context set to anonymous — dev mode only")
    _tenant_context.tenant_id = tenant_id


def clear_tenant_context() -> None:
    """Clear the current thread's tenant ID."""
    _tenant_context.tenant_id = None


def resolve_tenant_id() -> str:
    """Resolve the current tenant ID.

    FAIL-CLOSED: If no tenant is set and not in dev mode, raises RuntimeError.
    In dev mode (ZENIC_DEV_MODE=1), falls back to ANONYMOUS_TENANT with warning.

    Returns:
        The current tenant ID string.

    Raises:
        RuntimeError: If no tenant is set in production mode.
    """
    tenant_id = getattr(_tenant_context, "tenant_id", None)

    if tenant_id is not None:
        return tenant_id

    # No tenant set — fail-closed by default
    if os.environ.get("ZENIC_DEV_MODE") == "1":
        logger.warning(
            "resolve_tenant_id: No tenant context set — using anonymous. "
            "Set ZENIC_DEV_MODE=0 and call set_tenant_context() for production."
        )
        return ANONYMOUS_TENANT

    raise RuntimeError(
        "No tenant context set. Call set_tenant_context(tenant_id) before "
        "accessing tenant-scoped resources. In development, set ZENIC_DEV_MODE=1 "
        "to use anonymous tenant."
    )


def require_tenant() -> str:
    """Resolve tenant ID or raise — STRICT mode (no dev fallback).

    Use this for operations that MUST have a real tenant ID,
    even in development (e.g., data isolation, billing).

    Returns:
        The current tenant ID string.

    Raises:
        RuntimeError: If no tenant is set or tenant is anonymous.
    """
    tenant_id = getattr(_tenant_context, "tenant_id", None)
    if tenant_id is None or tenant_id == ANONYMOUS_TENANT:
        raise RuntimeError(
            "A real tenant ID is required for this operation. "
            "Anonymous tenant is not permitted."
        )
    return tenant_id
