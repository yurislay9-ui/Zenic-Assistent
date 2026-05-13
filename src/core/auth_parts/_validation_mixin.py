"""
Validation and utility mixin for AuthService.
"""

import re
import sqlite3

from ._imports import (
    logger, secrets, Path, datetime, timezone, threading,
    JOSE_AVAILABLE, PASSLIB_AVAILABLE,
)


class ValidationMixin:
    """Validation and utility for AuthService."""

    @staticmethod
    def _validate_registration(username: str, email: str, password: str) -> list:
        """Validate registration inputs. Returns error list (empty = valid)."""
        errors = []
        if not username or len(username) < 3:
            errors.append("Username must be at least 3 characters")
        if len(username) > 50:
            errors.append("Username must be at most 50 characters")
        if username and not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append("Username: only letters, numbers, underscores")
        if not email:
            errors.append("Email is required")
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append("Invalid email format")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters")
        if password and len(password) >= 8:
            if not (any(c.isupper() for c in password) and
                    any(c.islower() for c in password) and
                    any(c.isdigit() for c in password)):
                errors.append("Password must contain uppercase, lowercase, and a digit")
        return errors

    def get_stats(self) -> dict:
        """Get auth service statistics."""
        c = self._conn()
        with self._lock:
            return {
                "total_users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "active_users": c.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0],
                "revoked_tokens": c.execute("SELECT COUNT(*) FROM revoked_tokens").fetchone()[0],
                "active_api_keys": c.execute("SELECT COUNT(*) FROM api_keys WHERE active = 1").fetchone()[0],
                "jose_available": JOSE_AVAILABLE,
                "passlib_available": PASSLIB_AVAILABLE,
                "token_mode": "JWT" if JOSE_AVAILABLE else "HMAC-SHA256",
                "hash_mode": "bcrypt" if PASSLIB_AVAILABLE else "PBKDF2-SHA256",
            }

    def ensure_admin(self, username: str = "admin", password: str = "") -> dict:
        """Ensure an admin user exists. Creates one if no admin found."""
        c = self._conn()
        with self._lock:
            admin = c.execute("SELECT id FROM users WHERE role = 'admin' AND active = 1").fetchone()
            if admin:
                return {"message": "Admin user already exists", "user_id": admin["id"]}
            if not password:
                password = secrets.token_urlsafe(16)
            result = self.register_user(username, f"{username}@zenic.local", password, "admin")
            if "error" not in result:
                result["initial_password"] = password
                result["message"] = "Admin created. SAVE the password - it won't be shown again."
            return result
