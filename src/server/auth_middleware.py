"""
Auth middleware for FastAPI — JWT and API key authentication.

Extracts user identity from Authorization header or X-API-Key header,
verifies token/key, and attaches auth context to the request state.

Uses the existing AuthService (JWT + HMAC, RBAC, API keys).
Includes retry on transient DB errors via the resilience pattern.
"""

import logging
from typing import Any, Callable, Dict, Optional

from src.core.patterns.resilience.retry import RetryConfig, with_retry
from src.core.patterns.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)

logger = logging.getLogger(__name__)

# ── Retry config for auth DB operations ────────────────────
_AUTH_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=0.2,
    max_delay=2.0,
    backoff_strategy="exponential",
    jitter=True,
    retryable_exceptions=(Exception,),
)

# ── Circuit breaker for auth verification ──────────────────
_auth_breaker = CircuitBreaker(
    name="auth_verify",
    failure_threshold=5,
    recovery_timeout=30.0,
)


class AuthContext:
    """Resolved authentication context attached to each request.

    Attributes:
        user_id: Authenticated user ID (int).
        username: Username string.
        role: User role (viewer/user/manager/admin).
        permissions: Set of permission strings.
        tenant_id: Tenant ID the user belongs to (may be None).
        auth_method: How the user authenticated ('jwt' or 'api_key').
    """

    __slots__ = (
        "user_id", "username", "role", "permissions",
        "tenant_id", "auth_method",
    )

    def __init__(
        self,
        user_id: int,
        username: str = "",
        role: str = "viewer",
        permissions: Optional[set] = None,
        tenant_id: Optional[str] = None,
        auth_method: str = "jwt",
    ) -> None:
        self.user_id: int = user_id
        self.username: str = username
        self.role: str = role
        self.permissions: set = permissions or set()
        self.tenant_id: Optional[str] = tenant_id
        self.auth_method: str = auth_method

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def has_role(self, minimum_role: str) -> bool:
        from src.core.auth_parts._imports import ROLE_HIERARCHY
        return ROLE_HIERARCHY.get(self.role, -1) >= ROLE_HIERARCHY.get(minimum_role, -1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "permissions": list(self.permissions),
            "tenant_id": self.tenant_id,
            "auth_method": self.auth_method,
        }


def resolve_auth(
    auth_service: Any,
    authorization: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[AuthContext]:
    """Resolve authentication from headers.

    Tries JWT Bearer token first, then API key.

    Args:
        auth_service: AuthService instance.
        authorization: Value of Authorization header (e.g. 'Bearer xxx').
        api_key: Value of X-API-Key header.

    Returns:
        AuthContext on success, None on failure (no valid credentials).
    """
    # Try JWT Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = _auth_breaker.call(
                with_retry,
                auth_service.verify_token,
                _AUTH_RETRY,
                token,
                "access",
            )
        except CircuitOpenError:
            logger.warning("Auth circuit breaker OPEN — rejecting request")
            return None
        except Exception as e:
            logger.debug("JWT verification failed: %s", e)
            return None

        if "error" in payload:
            return None

        user_id = int(payload.get("sub", 0))
        role = payload.get("role", "viewer")

        # Get user details (with retry)
        try:
            user = _auth_breaker.call(
                with_retry,
                auth_service.get_user,
                _AUTH_RETRY,
                user_id,
            )
        except Exception:
            user = None

        if not user or not user.get("active"):
            return None

        # Get tenant
        tenant_id = user.get("tenant_id")
        permissions = auth_service.get_user_permissions(user_id)

        return AuthContext(
            user_id=user_id,
            username=user.get("username", ""),
            role=role,
            permissions=permissions,
            tenant_id=tenant_id,
            auth_method="jwt",
        )

    # Try API key
    if api_key:
        try:
            key_info = _auth_breaker.call(
                with_retry,
                auth_service.verify_api_key,
                _AUTH_RETRY,
                api_key,
            )
        except CircuitOpenError:
            logger.warning("Auth circuit breaker OPEN — rejecting request")
            return None
        except Exception as e:
            logger.debug("API key verification failed: %s", e)
            return None

        if not key_info:
            return None

        user_id = key_info.get("user_id", 0)
        role = key_info.get("role", "viewer")
        permissions = set(key_info.get("permissions", []))

        # Get tenant from user
        try:
            user = auth_service.get_user(user_id)
            tenant_id = user.get("tenant_id") if user else None
        except Exception:
            tenant_id = None

        return AuthContext(
            user_id=user_id,
            username=key_info.get("name", ""),
            role=role,
            permissions=permissions,
            tenant_id=tenant_id,
            auth_method="api_key",
        )

    return None


def require_auth(
    auth_service: Any,
    authorization: Optional[str] = None,
    api_key: Optional[str] = None,
    minimum_role: str = "user",
    permission: Optional[str] = None,
) -> Dict[str, Any]:
    """Require authentication with optional role/permission check.

    Returns:
        Dict with 'auth' (AuthContext) on success, or 'error' on failure.
    """
    ctx = resolve_auth(auth_service, authorization, api_key)
    if ctx is None:
        return {"error": "Authentication required", "status": 401}

    if minimum_role and not ctx.has_role(minimum_role):
        return {
            "error": f"Role '{minimum_role}' or higher required",
            "status": 403,
        }

    if permission and not ctx.has_permission(permission):
        return {
            "error": f"Permission '{permission}' required",
            "status": 403,
        }

    return {"auth": ctx}
