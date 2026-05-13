"""
API key authentication mixin for AuthService.

PERFORMANCE (H-03 fix): Removed per-call connection close() since
connections are now thread-local pooled in DbPasswordMixin._conn().
"""

from ._imports import (
    logger, secrets, hashlib, json, sqlite3,
    datetime, timezone, threading, API_KEY_PREFIX,
)


class ApiKeyMixin:
    """API key authentication for AuthService."""

    def create_api_key(self, user_id: int, name: str, permissions: list = None) -> dict:
        """Create API key. Plaintext shown only once."""
        user = self.get_user(user_id)
        if not user:
            return {"error": "User not found"}
        if not user.get("active"):
            return {"error": "User account is deactivated"}
        raw = secrets.token_hex(32)
        api_key = f"{API_KEY_PREFIX}{raw}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_id = secrets.token_hex(8)
        now = datetime.now(timezone.utc).isoformat()
        perms_json = json.dumps(permissions or [])
        c = self._conn()
        with self._lock:
            try:
                c.execute("INSERT INTO api_keys (id, user_id, name, key_hash, permissions, "
                          "active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                          (key_id, user_id, name, key_hash, perms_json, now))
                c.commit()
            except sqlite3.Error as e:
                return {"error": f"Database error: {e}"}
        logger.info(f"AuthService: API key created for user {user_id}: {name}")
        return {"key_id": key_id, "api_key": api_key, "name": name,
                "permissions": permissions or [],
                "message": "Save this key securely - it cannot be retrieved later"}

    def verify_api_key(self, api_key: str):
        """Verify API key. Returns identity dict or None."""
        if not api_key or not api_key.startswith(API_KEY_PREFIX):
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        c = self._conn()
        with self._lock:
            row = c.execute("SELECT id, user_id, name, key_hash, permissions, active "
                             "FROM api_keys WHERE key_hash = ? AND active = 1",
                             (key_hash,)).fetchone()
            if row and secrets.compare_digest(row["key_hash"], key_hash):
                user = self.get_user(row["user_id"])
                if not user or not user.get("active"):
                    return None
                now = datetime.now(timezone.utc).isoformat()
                c.execute("UPDATE api_keys SET last_used = ?, usage_count = usage_count + 1 "
                          "WHERE id = ?", (now, row["id"]))
                c.commit()
                try:
                    perms = json.loads(row["permissions"])
                except (json.JSONDecodeError, TypeError):
                    perms = []
                all_perms = self.get_user_permissions(row["user_id"]) | set(perms)
                return {"key_id": row["id"], "user_id": row["user_id"], "name": row["name"],
                        "role": user.get("role", "viewer"), "permissions": list(all_perms)}
            return None

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke API key by ID."""
        c = self._conn()
        with self._lock:
            try:
                cur = c.execute("UPDATE api_keys SET active = 0 WHERE id = ?", (key_id,))
                c.commit()
                return cur.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"AuthService: revoke_api_key error: {e}")
                return False

    def list_api_keys(self, user_id: int) -> list:
        """List API keys for user (without key values)."""
        c = self._conn()
        with self._lock:
            rows = c.execute("SELECT id, name, permissions, active, created_at, last_used, "
                             "usage_count FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
                             (user_id,)).fetchall()
            result = []
            for r in rows:
                try:
                    perms = json.loads(r["permissions"])
                except (json.JSONDecodeError, TypeError):
                    perms = []
                result.append({"key_id": r["id"], "name": r["name"], "permissions": perms,
                               "active": bool(r["active"]), "created_at": r["created_at"],
                               "last_used": r["last_used"], "usage_count": r["usage_count"]})
            return result
