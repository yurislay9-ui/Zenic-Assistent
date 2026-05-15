"""
ZENIC-AGENTS - AuthService Runtime (Phase 7.3 + SaaS Phase 1)

STUB: auth_parts module has been removed (external API auth deleted).
This module provides fallback constants and a no-op AuthService
for backward compatibility.

The original AuthService provided:
  - JWT + HMAC fallback tokens
  - RBAC, user management, token revocation
  - API key auth, multi-tenant support, plan-based quotas
  - SQLite-backed storage

All of these required external-facing auth (FastAPI middleware, JWT
for API access, API keys for external clients) which have been removed.
"""

import logging

logger = logging.getLogger(__name__)

# ── Fallback constants (were from auth_parts._imports) ──
ROLE_HIERARCHY = {
    "viewer": 0,
    "operador": 1,
    "gerente": 2,
    "admin": 3,
}

ROLE_PERMISSIONS: dict = {}

ACCESS_EXPIRE_MIN = 30
REFRESH_EXPIRE_DAYS = 7
PBKDF2_ITERATIONS = 100_000
API_KEY_PREFIX = "zk_"
PAGE_SIZE = 50

JOSE_AVAILABLE = False
PASSLIB_AVAILABLE = False
HAS_FASTAPI = False

# ── Fallback plan definitions (were from auth_parts._tenant_mixin) ──
PLAN_DEFINITIONS: dict = {}


class AuthService:
    """Stub AuthService — auth_parts module removed.

    Provides no-op methods for backward compatibility.
    All external-facing auth (JWT for API, API keys, FastAPI middleware)
    has been removed along with the server module.
    """

    def __init__(self, *args, **kwargs):
        logger.warning(
            "AuthService: auth_parts module removed — "
            "external API auth no longer available. Using stub."
        )

    def ensure_admin(self) -> None:
        """No-op — admin user creation no longer needed."""
        pass

    def authenticate(self, *args, **kwargs):
        """No-op — always returns None (no auth without external API)."""
        return None

    def register(self, *args, **kwargs):
        """No-op — user registration no longer available."""
        return None

    def login(self, *args, **kwargs):
        """No-op — login no longer available without external API."""
        return None

    def verify_token(self, *args, **kwargs):
        """No-op — token verification no longer available."""
        return None

    def create_api_key(self, *args, **kwargs):
        """No-op — API key creation no longer available."""
        return None

    def verify_api_key(self, *args, **kwargs):
        """No-op — API key verification no longer available."""
        return None


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
