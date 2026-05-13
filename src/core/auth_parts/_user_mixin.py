"""
User management mixin for AuthService.

PERFORMANCE (H-02 fix): Removed per-call connection close() since
connections are now thread-local pooled in DbPasswordMixin._conn().
"""

from ._imports import (
    logger, sqlite3, datetime, timezone, threading,
    ROLE_HIERARCHY, PAGE_SIZE,
)


class UserMixin:
    """User management for AuthService."""

    def register_user(self, username: str, email: str, password: str, role: str = "user") -> dict:
        """Register new user with validation."""
        errors = self._validate_registration(username, email, password)
        if errors:
            return {"error": "; ".join(errors)}
        if role not in ROLE_HIERARCHY:
            return {"error": f"Invalid role: {role}"}
        pw_hash = self.hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        c = self._conn()
        with self._lock:
            try:
                if c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                    return {"error": "Username already exists"}
                if c.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                    return {"error": "Email already registered"}
                cur = c.execute("INSERT INTO users (username, email, password_hash, role, active, "
                                "created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                                (username, email, pw_hash, role, now, now))
                uid = cur.lastrowid
                c.commit()
            except sqlite3.IntegrityError:
                return {"error": "Username or email already exists"}
            except sqlite3.Error as e:
                return {"error": f"Database error: {e}"}
        logger.info(f"AuthService: registered {username} (id={uid}, role={role})")
        return {"user_id": uid, "username": username, "email": email, "role": role,
                "message": "User registered successfully"}

    def login_user(self, username: str, password: str) -> dict:
        """Authenticate user and return tokens, or error dict."""
        c = self._conn()
        with self._lock:
            try:
                row = c.execute("SELECT id, username, email, password_hash, role, active "
                                "FROM users WHERE username = ? OR email = ?",
                                (username, username)).fetchone()
                if not row:
                    return {"error": "Invalid credentials"}
                if not row["active"]:
                    return {"error": "Account is deactivated"}
                if not self.verify_password(password, row["password_hash"]):
                    return {"error": "Invalid credentials"}
                uid, role = row["id"], row["role"]
                now = datetime.now(timezone.utc).isoformat()
                c.execute("UPDATE users SET last_login = ?, login_count = login_count + 1, "
                          "updated_at = ? WHERE id = ?", (now, now, uid))
                c.commit()
            except sqlite3.Error as e:
                return {"error": f"Database error: {e}"}
        logger.info(f"AuthService: login {row['username']}")
        return {
            "access_token": self.create_access_token(uid, role),
            "refresh_token": self.create_refresh_token(uid),
            "token_type": "bearer",
            "user": {"id": uid, "username": row["username"], "email": row["email"], "role": role},
        }

    def get_user(self, user_id: int):
        """Get user by ID (without password hash)."""
        c = self._conn()
        with self._lock:
            row = c.execute("SELECT id, username, email, role, active, created_at, "
                            "updated_at, last_login, login_count, tenant_id FROM users WHERE id = ?",
                            (user_id,)).fetchone()
            return dict(row) if row else None

    def update_user(self, user_id: int, **fields) -> dict:
        """Update user fields."""
        allowed = {"username", "email", "role", "active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return {"error": "No valid fields to update"}
        if "role" in updates and updates["role"] not in ROLE_HIERARCHY:
            return {"error": f"Invalid role: {updates['role']}"}
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [user_id]
        c = self._conn()
        with self._lock:
            try:
                if c.execute(f"UPDATE users SET {set_clause} WHERE id = ?", vals).rowcount == 0:
                    return {"error": "User not found"}
                c.commit()
            except sqlite3.IntegrityError:
                return {"error": "Username or email already exists"}
            except sqlite3.Error as e:
                return {"error": f"Database error: {e}"}
        return self.get_user(user_id) or {"error": "User not found after update"}

    def deactivate_user(self, user_id: int) -> bool:
        """Soft-delete user."""
        c = self._conn()
        with self._lock:
            try:
                cur = c.execute("UPDATE users SET active = 0, updated_at = ? WHERE id = ?",
                                (datetime.now(timezone.utc).isoformat(), user_id))
                c.commit()
                return cur.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"AuthService: deactivate error: {e}")
                return False

    def list_users(self, role: str = "", page: int = 1) -> list:
        """List users with optional role filter and pagination."""
        offset = (page - 1) * PAGE_SIZE
        c = self._conn()
        with self._lock:
            if role:
                rows = c.execute("SELECT id, username, email, role, active, created_at, "
                                 "last_login, login_count FROM users WHERE role = ? "
                                 "ORDER BY id LIMIT ? OFFSET ?", (role, PAGE_SIZE, offset)).fetchall()
            else:
                rows = c.execute("SELECT id, username, email, role, active, created_at, "
                                 "last_login, login_count FROM users ORDER BY id LIMIT ? OFFSET ?",
                                 (PAGE_SIZE, offset)).fetchall()
            return [dict(r) for r in rows]

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """Change password (requires current password)."""
        c = self._conn()
        with self._lock:
            try:
                row = c.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
                if not row or not self.verify_password(old_password, row["password_hash"]):
                    return False
                c.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                          (self.hash_password(new_password), datetime.now(timezone.utc).isoformat(), user_id))
                c.commit()
                logger.info(f"AuthService: password changed for user {user_id}")
                return True
            except sqlite3.Error as e:
                logger.error(f"AuthService: change_password error: {e}")
                return False

    def reset_password(self, user_id: int, new_password: str) -> bool:
        """Reset password (admin op)."""
        c = self._conn()
        with self._lock:
            try:
                cur = c.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                                (self.hash_password(new_password), datetime.now(timezone.utc).isoformat(), user_id))
                c.commit()
                return cur.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"AuthService: reset_password error: {e}")
                return False
