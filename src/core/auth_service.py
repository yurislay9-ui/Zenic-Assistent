"""
ZENIC-AGENTS - AuthService Runtime (Phase 7.3 + SaaS Phase 1)

Runtime authentication service for the orchestrator and generated apps.
JWT + HMAC fallback tokens, RBAC, user management, token revocation,
API key auth, multi-tenant support, plan-based quotas.
Uses SQLite. Zero hard deps beyond stdlib.

Compatible con Termux + Android.
"""

from .auth_parts import *  # noqa: F401,F403
from .auth_parts import AuthService  # explicit
from .auth_parts._imports import (
    ROLE_HIERARCHY, ROLE_PERMISSIONS, ACCESS_EXPIRE_MIN,
    REFRESH_EXPIRE_DAYS, PBKDF2_ITERATIONS, API_KEY_PREFIX, PAGE_SIZE,
    JOSE_AVAILABLE, PASSLIB_AVAILABLE, HAS_FASTAPI,
)
from .auth_parts._tenant_mixin import PLAN_DEFINITIONS

__all__ = [
    "AuthService",
    "ROLE_HIERARCHY",
    "ROLE_PERMISSIONS",
    "ACCESS_EXPIRE_MIN",
    "REFRESH_EXPIRE_DAYS",
    "PBKDF2_ITERATIONS",
    "API_KEY_PREFIX",
    "PAGE_SIZE",
    "JOSE_AVAILABLE",
    "PASSLIB_AVAILABLE",
    "HAS_FASTAPI",
    "PLAN_DEFINITIONS",
]
