"""
Tenant module — Multi-tenancy context, isolation, and feature gating.

Phase 2: Real Multitenancy for Zenic-Agents SaaS.

Key components:
- TenantContext: Carries tenant_id, plan, quotas through the entire pipeline
- TenantIsolation: Enforces row-level tenant isolation on all DB queries
- FeatureGate: Enforces plan-based feature access at endpoint and pipeline level
- set_current_tenant / get_current_tenant / clear_current_tenant: Thread-local context
- require_feature: Convenience function for feature gating in endpoints
- FeatureNotAvailableError: Exception for insufficient plan level
"""

from ._context import (
    TenantContext,
    set_current_tenant,
    get_current_tenant,
    clear_current_tenant,
)
from ._isolation import TenantIsolation
from ._feature_gate import FeatureGate, require_feature, FeatureNotAvailableError

__all__ = [
    "TenantContext",
    "TenantIsolation",
    "FeatureGate",
    "require_feature",
    "FeatureNotAvailableError",
    "set_current_tenant",
    "get_current_tenant",
    "clear_current_tenant",
]
