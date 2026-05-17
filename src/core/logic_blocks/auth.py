"""
ZENIC-AGENTS - Auth Logic Blocks

Authentication and authorization blocks: login, register, verify, RBAC.
"""

import json
import time
import hashlib
import logging
from typing import Any, Dict

from .chain import LogicBlock

logger = logging.getLogger(__name__)


def _sanitize(value: str, visible: int = 4) -> str:
    """Show only last N characters of a secret."""
    if not value or len(value) <= visible:
        return "***"
    return f"***{value[-visible:]}"


# ============================================================
#  AUTH BLOCKS (4)
# ============================================================


class AuthLoginBlock(LogicBlock):
    """Verifica credenciales y retorna token JWT."""

    name = "auth_login"
    category = "auth"
    description = "Verify credentials and return authentication token"
    inputs = ["username", "password"]
    outputs = ["token", "user_id", "role"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            username = data.get("username", data.get("email", ""))
            password = data.get("password", "")
            secret = context.get("secret_key", "change-this-in-production")

            if not username or not password:
                return {"success": False, "error": "Username and password required"}

            # Verify against database
            db = context.get("db", None)
            user = None

            if db is not None:
                try:
                    cursor = db.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT id, username, password_hash, role FROM users WHERE username = ? OR email = ?",
                        (username, username)
                    )
                    row = cursor.fetchone()
                    if row:
                        user = dict(row) if hasattr(row, 'keys') else {
                            "id": row[0], "username": row[1], "password_hash": row[2], "role": row[3]
                        }
                except Exception as db_err:
                    logger.debug(f"AuthLoginBlock: DB lookup failed: {db_err}")

            if user:
                # Verify password hash
                stored_hash = user.get("password_hash", "")
                if self._verify_password(password, stored_hash):
                    token = self._generate_token(user, secret)
                    logger.debug(f"AuthLoginBlock: Login success for {_sanitize(username)}")
                    return {
                        "success": True,
                        "token": token,
                        "user_id": user["id"],
                        "username": user["username"],
                        "role": user.get("role", "user"),
                    }
                else:
                    logger.warning(f"AuthLoginBlock: Invalid password for {_sanitize(username)}")
                    return {"success": False, "error": "Invalid credentials"}

            # No user found
            logger.warning(f"AuthLoginBlock: User not found: {_sanitize(username)}")
            return {"success": False, "error": "Invalid credentials"}

        except Exception as e:
            return {"success": False, "error": f"AuthLoginBlock: {str(e)}"}

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        """Verifica password contra hash almacenado."""
        import hmac as hmac_mod
        try:
            if ":" in stored_hash:
                salt, hash_val = stored_hash.split(":", 1)
                dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
                return hmac_mod.compare_digest(dk.hex(), hash_val)
            # Fallback: plain comparison (dev only)
            return password == stored_hash
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _generate_token(user: Dict, secret: str) -> str:
        """Genera JWT token simple."""
        try:
            import base64
            header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode()
            payload = base64.urlsafe_b64encode(json.dumps({
                "sub": user["id"], "username": user["username"],
                "role": user.get("role", "user"), "exp": int(time.time()) + 86400,
                "iat": int(time.time()),
            }, default=str).encode()).decode()
            import hmac as hmac_mod
            sig = hmac_mod.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()
            return f"{header}.{payload}.{sig}"
        except Exception:
            return hashlib.sha256(f"{user['id']}:{time.time()}:{secret}".encode()).hexdigest()


class AuthRegisterBlock(LogicBlock):
    """Registra nuevo usuario con validacion."""

    name = "auth_register"
    category = "auth"
    description = "Register new user with validation"
    inputs = ["username", "email", "password", "role"]
    outputs = ["user_id", "status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            username = data.get("username", "")
            email = data.get("email", "")
            password = data.get("password", "")
            role = data.get("role", "user")

            # Validate required fields
            errors = []
            if not username or len(username) < 3:
                errors.append("Username must be at least 3 characters")
            if not email or "@" not in email:
                errors.append("Valid email is required")
            if not password or len(password) < 6:
                errors.append("Password must be at least 6 characters")
            if errors:
                return {"success": False, "error": "; ".join(errors)}

            # Hash password
            import secrets
            salt = secrets.token_hex(16)
            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            password_hash = f"{salt}:{dk.hex()}"

            # Check uniqueness and insert
            db = context.get("db", None)
            if db is not None:
                try:
                    # Check if user/email already exists
                    cursor = db.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT id FROM users WHERE username = ? OR email = ?",
                        (username, email)
                    )
                    if cursor.fetchone():
                        return {"success": False, "error": "Username or email already exists"}

                    cursor = db.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                        (username, email, password_hash, role)
                    )
                    user_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
                    db.commit() if hasattr(db, 'commit') else None

                    logger.debug(f"AuthRegisterBlock: Registered user {_sanitize(username)} (id={user_id})")
                    return {
                        "success": True,
                        "user_id": user_id,
                        "username": username,
                        "email": email,
                        "role": role,
                        "status": "registered",
                    }
                except Exception as db_err:
                    logger.warning(f"AuthRegisterBlock: DB error: {db_err}")
                    return {"success": False, "error": f"Registration failed: {str(db_err)}"}

            # Fallback: return user data without DB
            user_id = hashlib.md5(f"{username}{email}".encode()).hexdigest()[:8]
            logger.debug(f"AuthRegisterBlock: Fallback register {_sanitize(username)}")
            return {
                "success": True,
                "user_id": user_id,
                "username": username,
                "email": email,
                "role": role,
                "status": "registered_no_db",
            }
        except Exception as e:
            return {"success": False, "error": f"AuthRegisterBlock: {str(e)}"}


class AuthVerifyBlock(LogicBlock):
    """Verifica token JWT."""

    name = "auth_verify"
    category = "auth"
    description = "Verify JWT authentication token"
    inputs = ["token"]
    outputs = ["valid", "user_id", "role", "decoded"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            token = data.get("token", "")
            secret = context.get("secret_key", "change-this-in-production")

            if not token:
                return {"success": False, "error": "No token provided", "valid": False}

            # Simple JWT verification
            try:
                import base64
                import hmac as hmac_mod

                parts = token.split(".")
                if len(parts) != 3:
                    return {"success": True, "valid": False, "error": "Invalid token format"}

                header, payload, signature = parts

                # Verify signature
                expected_sig = hmac_mod.new(
                    secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
                ).hexdigest()

                if not hmac_mod.compare_digest(signature, expected_sig):
                    return {"success": True, "valid": False, "error": "Invalid signature"}

                # Decode payload
                padding = "=" * (4 - len(payload) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload + padding))

                # Check expiration
                if decoded.get("exp", 0) < time.time():
                    return {"success": True, "valid": False, "error": "Token expired"}

                logger.debug(f"AuthVerifyBlock: Token valid for user {_sanitize(str(decoded.get('sub', '')))}")
                return {
                    "success": True,
                    "valid": True,
                    "user_id": decoded.get("sub"),
                    "username": decoded.get("username"),
                    "role": decoded.get("role", "user"),
                    "decoded": decoded,
                }

            except Exception as token_err:
                logger.warning(f"AuthVerifyBlock: Token verification failed: {_sanitize(str(token_err))}")
                return {"success": True, "valid": False, "error": f"Token verification failed: {str(token_err)}"}

        except Exception as e:
            return {"success": False, "error": f"AuthVerifyBlock: {str(e)}"}


class AuthRBACBlock(LogicBlock):
    """Verifica permisos basados en roles."""

    name = "auth_rbac"
    category = "auth"
    description = "Check role-based access control permissions"
    inputs = ["user_role", "resource", "action"]
    outputs = ["allowed", "reason"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_role = data.get("user_role", data.get("role", "guest"))
            resource = data.get("resource", "")
            action = data.get("action", "read")  # read, write, delete, admin

            # Default RBAC policy
            default_policy = {
                "admin": {"*": ["read", "write", "delete", "admin"]},
                "manager": {
                    "*": ["read", "write"],
                    "users": ["read"],
                    "settings": ["read"],
                },
                "user": {
                    "items": ["read", "write"],
                    "reports": ["read"],
                    "users": ["read"],
                    "settings": [],
                },
                "guest": {
                    "items": ["read"],
                    "reports": ["read"],
                    "*": [],
                },
            }

            # Load custom policy from context if available
            policy = context.get("rbac_policy", default_policy)

            role_permissions = policy.get(user_role, policy.get("guest", {}))

            # Check wildcard resource first
            wildcard_actions = role_permissions.get("*", [])
            resource_actions = role_permissions.get(resource, [])

            allowed_actions = set(wildcard_actions + resource_actions)

            # If wildcard includes the specific action
            allowed = action in allowed_actions or "admin" in allowed_actions

            reason = ""
            if not allowed:
                reason = f"Role '{user_role}' does not have '{action}' permission on '{resource}'"
                logger.debug(f"AuthRBACBlock: DENIED role={user_role}, action={action}, resource={resource}")
            else:
                logger.debug(f"AuthRBACBlock: ALLOWED role={user_role}, action={action}, resource={resource}")

            return {
                "success": True,
                "allowed": allowed,
                "reason": reason,
                "user_role": user_role,
                "resource": resource,
                "action": action,
            }
        except Exception as e:
            return {"success": False, "error": f"AuthRBACBlock: {str(e)}"}
