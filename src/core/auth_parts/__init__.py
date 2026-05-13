"""
AuthService — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.auth_service import AuthService``
still works exactly as before.
"""

import os
import sys
import threading
from pathlib import Path

from ._imports import (
    logger, secrets, JOSE_AVAILABLE, PASSLIB_AVAILABLE,
)
from ._db_mixin import DbPasswordMixin
from ._token_mixin import TokenMixin
from ._user_mixin import UserMixin
from ._rbac_mixin import RbacMixin
from ._api_key_mixin import ApiKeyMixin
from ._validation_mixin import ValidationMixin
from ._tenant_mixin import TenantMixin

# Placeholder secrets that MUST be changed in production
_INSECURE_SECRETS = frozenset({
    "CHANGE_ME_GENERATE_A_SECURE_JWT_SECRET",
    "CHANGE_ME_GENERATE_A_SECURE_SECRET",
    "changeme",
    "secret",
    "jwt_secret",
})


class AuthService(DbPasswordMixin, TokenMixin, UserMixin, RbacMixin,
                  ApiKeyMixin, ValidationMixin, TenantMixin):
    """
    Runtime authentication service for ZENIC-AGENTS.

    Provides JWT authentication, user management, RBAC, and
    multi-tenant support. Uses SQLite for user storage.
    Works with or without python-jose and passlib (has fallbacks).
    """

    def __init__(self, db_path: str = "", secret_key: str = ""):
        if db_path:
            self._db_path = db_path
        else:
            d = Path.home() / ".zenic_agents" / "db"
            d.mkdir(parents=True, exist_ok=True)
            self._db_path = str(d / "auth.sqlite")

        self._secret_key = secret_key or os.environ.get("ZENIC_AUTH_SECRET", "")

        # ── Production secret validation ──────────────────────
        # In production mode, REFUSE to start with a placeholder secret.
        if os.environ.get("ZENIC_ENV") == "production":
            if self._secret_key in _INSECURE_SECRETS:
                logger.critical(
                    "SECURITY: ZENIC_AUTH_SECRET is set to a known placeholder. "
                    "The application REFUSES to start with an insecure secret in production. "
                    "Generate a secure secret with: "
                    "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
                sys.exit(1)

        if not self._secret_key:
            kf = Path(self._db_path).parent / ".auth_secret"
            if kf.exists():
                self._secret_key = kf.read_text().strip()
            else:
                self._secret_key = secrets.token_hex(32)
                kf.write_text(self._secret_key); kf.chmod(0o600)

        self._lock = threading.RLock()
        self.init_db()
        self.init_tenant_tables()
        logger.info(f"AuthService: init (jose={JOSE_AVAILABLE}, passlib={PASSLIB_AVAILABLE}, tenants=enabled)")


__all__ = ["AuthService"]
