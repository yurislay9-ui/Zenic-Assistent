"""
FeatureGate — Enforces plan-based feature access.

Provides decorators and context managers that check whether the current
tenant's plan includes a specific feature before allowing an operation.

This is the enforcement layer for SaaS monetization:
- Free plan: basic_pipeline, chat_completions only
- Pro plan: + app_generation, automation, schema_design, think, reason
- Enterprise plan: everything (features = "all")

Usage in FastAPI endpoints:
    @app.post("/v1/generate/app")
    async def generate_app(request: Request, auth_ctx = Depends(require_auth_dep)):
        require_feature("app_generation", auth_ctx)
        ...

Usage in pipeline code:
    from src.core.tenant import require_feature, FeatureGate
    FeatureGate.check("automation_generation", tenant_plan="free")
    # raises FeatureNotAvailableError if plan doesn't include it
"""

import logging
import functools
from typing import Any, Callable, Optional, Set

from ._context import get_current_tenant, TenantContext
from src.core.auth_parts._tenant_mixin import PLAN_DEFINITIONS

logger = logging.getLogger(__name__)


class FeatureNotAvailableError(PermissionError):
    """Raised when a tenant's plan doesn't include the requested feature.

    This is a PermissionError subclass so that FastAPI exception handlers
    can catch it and return a 403 with a helpful message about upgrading.
    """

    def __init__(self, feature: str, plan: str, required_plans: Optional[Set[str]] = None):
        self.feature = feature
        self.plan = plan
        self.required_plans = required_plans or set()
        upgrade_msg = ""
        if required_plans:
            upgrade_msg = f" Upgrade to {', '.join(sorted(required_plans))} to access this feature."
        super().__init__(
            f"Feature '{feature}' is not available on the '{plan}' plan.{upgrade_msg}"
        )


class FeatureGate:
    """Static utility for feature gating based on tenant plan."""

    # Map feature → minimum plan required
    # (used as fallback when PLAN_DEFINITIONS doesn't specify features list)
    FEATURE_MINIMUM_PLAN: dict = {
        "basic_pipeline": "free",
        "chat_completions": "free",
        "app_generation": "pro",
        "automation_generation": "pro",
        "schema_design": "pro",
        "thinking_engine": "pro",
        "reasoning_engine": "pro",
        "logic_chains": "pro",
        "advanced_orchestration": "enterprise",
        "custom_models": "enterprise",
        "audit_log": "enterprise",
        "sso": "enterprise",
        "priority_support": "enterprise",
    }

    PLAN_RANK: dict = {"free": 0, "pro": 1, "enterprise": 2}

    @staticmethod
    def check(
        feature: str,
        tenant_plan: Optional[str] = None,
        tenant_ctx: Optional[TenantContext] = None,
    ) -> bool:
        """Check if a feature is available for the given plan.

        Args:
            feature: Feature identifier (e.g. 'app_generation').
            tenant_plan: Override plan (defaults to current context).
            tenant_ctx: Override TenantContext (defaults to thread-local).

        Returns:
            True if the feature is available.

        Raises:
            FeatureNotAvailableError if the feature is not available.
        """
        ctx = tenant_ctx or get_current_tenant()
        plan = tenant_plan or ctx.plan

        # Enterprise always has everything
        if plan == "enterprise":
            return True

        # Check feature list from plan definition
        plan_def = PLAN_DEFINITIONS.get(plan, {})
        plan_features = plan_def.get("features", [])

        if plan_features == "all":
            return True

        if isinstance(plan_features, list) and feature in plan_features:
            return True

        # Check context features (from TenantContext)
        if ctx.has_feature(feature):
            return True

        # Check minimum plan requirement
        min_plan = FeatureGate.FEATURE_MINIMUM_PLAN.get(feature)
        if min_plan:
            current_rank = FeatureGate.PLAN_RANK.get(plan, -1)
            required_rank = FeatureGate.PLAN_RANK.get(min_plan, 99)
            if current_rank >= required_rank:
                return True

            # Determine which plans include this feature
            required_plans = {
                p for p, r in FeatureGate.PLAN_RANK.items()
                if r >= required_rank
            }
            raise FeatureNotAvailableError(feature, plan, required_plans)

        # Feature not found in any plan definition — deny by default
        raise FeatureNotAvailableError(feature, plan)

    @staticmethod
    def is_available(
        feature: str,
        tenant_plan: Optional[str] = None,
        tenant_ctx: Optional[TenantContext] = None,
    ) -> bool:
        """Non-throwing version of check().

        Returns True if the feature is available, False otherwise.
        """
        try:
            return FeatureGate.check(feature, tenant_plan, tenant_ctx)
        except FeatureNotAvailableError:
            return False

    @staticmethod
    def get_available_features(plan: str) -> Set[str]:
        """Get all features available for a plan.

        Args:
            plan: Plan name ('free', 'pro', 'enterprise').

        Returns:
            Set of feature identifiers.
        """
        plan_def = PLAN_DEFINITIONS.get(plan, {})
        plan_features = plan_def.get("features", [])

        if plan_features == "all":
            return set(FeatureGate.FEATURE_MINIMUM_PLAN.keys())

        if isinstance(plan_features, list):
            return set(plan_features)

        return set()


def require_feature(
    feature: str,
    auth_ctx: Optional[Any] = None,
) -> None:
    """Require a feature to be available for the current tenant.

    This is the main entry point for feature gating in endpoints
    and pipeline code. It reads the current TenantContext from
    thread-local storage.

    Raises:
        FeatureNotAvailableError: If the feature is not available.
    """
    tenant_ctx = None
    if auth_ctx is not None:
        # Convert AuthContext to TenantContext if needed
        if isinstance(auth_ctx, TenantContext):
            tenant_ctx = auth_ctx
        elif hasattr(auth_ctx, "tenant_id"):
            # It's an AuthContext from auth_middleware
            tenant_ctx = TenantContext.from_auth_context(auth_ctx)

    FeatureGate.check(feature, tenant_ctx=tenant_ctx)


def feature_gate(feature: str) -> Callable:
    """Decorator that gates a function behind a feature check.

    Usage:
        @feature_gate("app_generation")
        async def generate_app(request):
            ...

    Raises:
        FeatureNotAvailableError: If the feature is not available.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            FeatureGate.check(feature)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            FeatureGate.check(feature)
            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
