"""
TenantContext — Carries tenant identity through the entire pipeline.

This is THE central object for multitenancy. Every request creates one
and it flows: HTTP request → FastAPI middleware → orchestrator.execute()
→ agents → SmartMemory → MerkleLedger → TheoremCache.

Never None in production — if no auth, use TenantContext.anonymous().

Thread-safety: TenantContext is immutable after creation. All fields
are read-only. To change tenant mid-request, create a new context.
"""

import threading
from typing import Any, ClassVar, Dict, FrozenSet, List, Optional
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TenantContext:
    """Immutable tenant context that flows through the pipeline.

    Attributes:
        tenant_id: Unique tenant identifier (e.g. 'tn_abc123').
                   None for anonymous requests.
        user_id: Authenticated user ID. None for anonymous.
        username: Username string. Empty for anonymous.
        role: User role ('viewer', 'user', 'manager', 'admin').
        plan: Tenant plan ('free', 'pro', 'enterprise').
        quotas: Plan quota definitions (from PLAN_DEFINITIONS).
        features: Set of features allowed for this plan.
        permissions: Set of permission strings for this user.
        auth_method: How the user authenticated ('jwt', 'api_key', 'none').
        is_authenticated: Whether the user is authenticated.
        extra: Arbitrary metadata (request_id, IP, etc.).
    """

    tenant_id: Optional[str] = None
    user_id: Optional[int] = None
    username: str = ""
    role: str = "viewer"
    plan: str = "free"
    quotas: Dict[str, Any] = field(default_factory=dict)
    features: FrozenSet[str] = field(default_factory=frozenset)
    permissions: FrozenSet[str] = field(default_factory=frozenset)
    auth_method: str = "none"
    is_authenticated: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    # ── Class-level defaults (ClassVar so dataclass ignores them) ──

    _ANONYMOUS_QUOTAS: ClassVar[Dict[str, Any]] = {
        "max_requests_per_minute": 5,
        "max_requests_per_day": 100,
        "max_tokens_per_day": 10000,
        "max_concurrent": 1,
        "max_storage_mb": 10,
        "features": ["basic_pipeline"],
    }

    _ANONYMOUS_FEATURES: ClassVar[FrozenSet[str]] = frozenset({"basic_pipeline", "chat_completions"})

    # ── Factory methods ───────────────────────────────────

    @classmethod
    def anonymous(cls) -> "TenantContext":
        """Create an anonymous (unauthenticated) tenant context.

        Anonymous users get the most restricted quotas — they are
        effectively on a 'free' plan with even lower limits. This
        prevents abuse from unauthenticated traffic.
        """
        return cls(
            tenant_id=None,
            user_id=None,
            username="anonymous",
            role="viewer",
            plan="free",
            quotas=cls._ANONYMOUS_QUOTAS,
            features=cls._ANONYMOUS_FEATURES,
            permissions=frozenset({"read"}),
            auth_method="none",
            is_authenticated=False,
        )

    @classmethod
    def from_auth_context(
        cls,
        auth_ctx: Any,
        plan: str = "free",
        quotas: Optional[Dict[str, Any]] = None,
        features: Optional[List[str]] = None,
    ) -> "TenantContext":
        """Create a TenantContext from an AuthContext (auth_middleware).

        This bridges Phase 1 (AuthContext) and Phase 2 (TenantContext).

        Args:
            auth_ctx: AuthContext from auth_middleware.
            plan: Tenant plan from AuthService.
            quotas: Plan quota definitions.
            features: Feature list for this plan.
        """
        feature_set = frozenset(features) if features else frozenset()
        perm_set = frozenset(auth_ctx.permissions) if hasattr(auth_ctx, "permissions") else frozenset()

        return cls(
            tenant_id=auth_ctx.tenant_id if hasattr(auth_ctx, "tenant_id") else None,
            user_id=auth_ctx.user_id if hasattr(auth_ctx, "user_id") else None,
            username=auth_ctx.username if hasattr(auth_ctx, "username") else "",
            role=auth_ctx.role if hasattr(auth_ctx, "role") else "viewer",
            plan=plan,
            quotas=quotas or {},
            features=feature_set,
            permissions=perm_set,
            auth_method=auth_ctx.auth_method if hasattr(auth_ctx, "auth_method") else "none",
            is_authenticated=True,
        )

    # ── Accessor helpers ──────────────────────────────────

    @property
    def is_anonymous(self) -> bool:
        """Whether this context represents an anonymous request."""
        return not self.is_authenticated or self.tenant_id is None

    @property
    def effective_tenant_id(self) -> str:
        """Tenant ID or '__anonymous__' for unauthenticated requests.

        Useful for DB queries that need a string tenant_id value.
        """
        return self.tenant_id or "__anonymous__"

    @property
    def max_rpm(self) -> int:
        """Max requests per minute from plan quotas."""
        return self.quotas.get("max_requests_per_minute", 5)

    @property
    def max_rpd(self) -> int:
        """Max requests per day from plan quotas."""
        return self.quotas.get("max_requests_per_day", 100)

    @property
    def max_concurrent(self) -> int:
        """Max concurrent requests from plan quotas."""
        return self.quotas.get("max_concurrent", 1)

    @property
    def max_storage_mb(self) -> int:
        """Max storage in MB from plan quotas."""
        return self.quotas.get("max_storage_mb", 10)

    def has_feature(self, feature: str) -> bool:
        """Check if the current plan includes a specific feature.

        Enterprise plans with features='all' always return True.
        """
        if self.features == frozenset({"all"}) or "all" in self.features:
            return True
        return feature in self.features

    def has_permission(self, perm: str) -> bool:
        """Check if the user has a specific permission."""
        return perm in self.permissions

    def has_role(self, minimum_role: str) -> bool:
        """Check if the user has at least the minimum role."""
        try:
            from src.core.auth_parts._imports import ROLE_HIERARCHY
            return ROLE_HIERARCHY.get(self.role, -1) >= ROLE_HIERARCHY.get(minimum_role, -1)
        except ImportError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context for logging/debugging."""
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "plan": self.plan,
            "is_authenticated": self.is_authenticated,
            "auth_method": self.auth_method,
            "max_rpm": self.max_rpm,
            "max_rpd": self.max_rpd,
            "features": list(self.features),
        }

    def to_pipeline_context(self) -> Dict[str, Any]:
        """Create a dict suitable for injection into the DAG pipeline ctx.

        This is the bridge between TenantContext and the DAGOrchestrator's
        internal ctx dict. It adds a 'tenant' key with all relevant fields.
        """
        return {
            "tenant": {
                "tenant_id": self.effective_tenant_id,
                "user_id": self.user_id,
                "username": self.username,
                "role": self.role,
                "plan": self.plan,
                "is_authenticated": self.is_authenticated,
                "max_rpm": self.max_rpm,
                "max_rpd": self.max_rpd,
                "max_concurrent": self.max_concurrent,
                "max_storage_mb": self.max_storage_mb,
                "features": list(self.features),
                "permissions": list(self.permissions),
            },
        }


# ── Thread-local storage for TenantContext ────────────────
# Allows any code in the call stack to access the current tenant
# without explicitly passing it as a parameter. This is essential
# for deeply nested code (e.g. SmartMemory.save()) that needs
# tenant_id but doesn't receive it as a parameter.

_thread_local: threading.local = threading.local()


def set_current_tenant(ctx: TenantContext) -> None:
    """Set the TenantContext for the current thread.

    Called at the beginning of each HTTP request by the middleware.
    Cleared at the end of the request.
    """
    _thread_local.tenant_ctx = ctx


def get_current_tenant() -> TenantContext:
    """Get the TenantContext for the current thread.

    Returns anonymous context if none is set (should not happen
    in production, but provides safe fallback).
    """
    ctx = getattr(_thread_local, "tenant_ctx", None)
    if ctx is None:
        return TenantContext.anonymous()
    return ctx


def clear_current_tenant() -> None:
    """Clear the TenantContext for the current thread.

    Called at the end of each HTTP request.
    """
    _thread_local.tenant_ctx = None
