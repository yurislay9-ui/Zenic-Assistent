"""TenantMixin CRUD methods: schema init, tenant CRUD, user-tenant assignment."""

from ._plans import PLAN_DEFINITIONS
from .._imports import (
    logger, sqlite3, secrets, json, threading,
    datetime, timezone, ROLE_HIERARCHY,
)
from typing import Dict, List, Optional, Any


class TenantCrudMixin:
    """Tenant schema initialization and CRUD operations.

    Requires ``_conn()``, ``_lock``, and ``init_db()`` from other mixins.
    Call ``init_tenant_tables()`` from ``init_db()`` to create the schema.
    """

    # ── Schema initialization ──────────────────────────────

    def init_tenant_tables(self) -> None:
        """Create tenants and tenant_usage tables if not exists.

        Must be called from ``init_db()`` after the core tables exist.
        Also migrates the users table to add ``tenant_id`` column.
        """
        c = self._conn()
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                config TEXT DEFAULT '{}',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            c.execute("""CREATE TABLE IF NOT EXISTS tenant_usage (
                tenant_id TEXT NOT NULL,
                date TEXT NOT NULL,
                requests_count INTEGER DEFAULT 0,
                tokens_count INTEGER DEFAULT 0,
                compute_seconds REAL DEFAULT 0.0,
                storage_mb REAL DEFAULT 0.0,
                PRIMARY KEY (tenant_id, date),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id))""")
            # Add tenant_id column to users (migration-safe)
            cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
            if "tenant_id" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN tenant_id TEXT REFERENCES tenants(id)")
            # Indexes
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_tenants_name ON tenants(name)",
                "CREATE INDEX IF NOT EXISTS idx_tenants_plan ON tenants(plan)",
                "CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants(active)",
                "CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)",
                "CREATE INDEX IF NOT EXISTS idx_usage_tenant_date ON tenant_usage(tenant_id, date)",
            ]:
                c.execute(idx_sql)
            c.commit()
            logger.info("AuthService: tenant tables initialized")
        except sqlite3.Error as e:
            logger.error("AuthService: init_tenant_tables error: %s", e)

    # ── Tenant CRUD ────────────────────────────────────────

    def create_tenant(
        self,
        name: str,
        plan: str = "free",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new tenant with the given plan.

        Args:
            name: Human-readable tenant name (e.g. company name).
            plan: One of 'free', 'pro', 'enterprise'.
            config: Optional per-tenant config overrides.

        Returns:
            Dict with tenant info on success, or ``{'error': ...}`` on failure.
        """
        if plan not in PLAN_DEFINITIONS:
            return {"error": f"Invalid plan: {plan}. Must be one of: {list(PLAN_DEFINITIONS)}"}
        if not name or len(name) < 2:
            return {"error": "Tenant name must be at least 2 characters"}

        tenant_id = f"tn_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc).isoformat()
        config_json = json.dumps(config or {})

        c = self._conn()
        try:
            with self._lock:
                c.execute(
                    "INSERT INTO tenants (id, name, plan, config, active, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (tenant_id, name, plan, config_json, now, now),
                )
                c.commit()
            logger.info("AuthService: tenant created %s (%s, plan=%s)", tenant_id, name, plan)
            return {
                "tenant_id": tenant_id,
                "name": name,
                "plan": plan,
                "quotas": PLAN_DEFINITIONS[plan],
                "message": "Tenant created successfully",
            }
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID. Returns dict or None."""
        c = self._conn()
        try:
            row = c.execute(
                "SELECT id, name, plan, config, active, created_at, updated_at "
                "FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            try:
                result["config"] = json.loads(result.get("config", "{}"))
            except (json.JSONDecodeError, TypeError):
                result["config"] = {}
            result["quotas"] = PLAN_DEFINITIONS.get(result["plan"], PLAN_DEFINITIONS["free"])
            return result
        except sqlite3.Error as e:
            logger.error("AuthService: get_tenant error: %s", e)
            return None

    def update_tenant(self, tenant_id: str, **fields: Any) -> Dict[str, Any]:
        """Update tenant fields (name, plan, config, active)."""
        allowed = {"name", "plan", "config", "active"}
        updates: Dict[str, Any] = {}
        for k, v in fields.items():
            if k in allowed:
                if k == "plan" and v not in PLAN_DEFINITIONS:
                    return {"error": f"Invalid plan: {v}"}
                if k == "config":
                    updates[k] = json.dumps(v)
                else:
                    updates[k] = v
        if not updates:
            return {"error": "No valid fields to update"}

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [tenant_id]

        c = self._conn()
        try:
            with self._lock:
                if c.execute(f"UPDATE tenants SET {set_clause} WHERE id = ?", vals).rowcount == 0:
                    return {"error": "Tenant not found"}
                c.commit()
            return self.get_tenant(tenant_id) or {"error": "Tenant not found after update"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}

    def deactivate_tenant(self, tenant_id: str) -> bool:
        """Soft-delete a tenant (sets active=0)."""
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute(
                    "UPDATE tenants SET active = 0, updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), tenant_id),
                )
                c.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error("AuthService: deactivate_tenant error: %s", e)
            return False

    def list_tenants(self, plan: str = "", active_only: bool = True) -> List[Dict[str, Any]]:
        """List tenants with optional plan filter."""
        c = self._conn()
        try:
            query = "SELECT id, name, plan, config, active, created_at, updated_at FROM tenants"
            conditions: List[str] = []
            params: List[Any] = []
            if active_only:
                conditions.append("active = 1")
            if plan:
                conditions.append("plan = ?")
                params.append(plan)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"
            rows = c.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error("AuthService: list_tenants error: %s", e)
            return []

    # ── User-Tenant assignment ──────────────────────────────

    def assign_user_to_tenant(self, user_id: int, tenant_id: str) -> Dict[str, Any]:
        """Assign a user to a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}
        if not tenant.get("active"):
            return {"error": "Tenant is deactivated"}
        c = self._conn()
        try:
            with self._lock:
                if c.execute("UPDATE users SET tenant_id = ?, updated_at = ? WHERE id = ?",
                             (tenant_id, datetime.now(timezone.utc).isoformat(), user_id)).rowcount == 0:
                    return {"error": "User not found"}
                c.commit()
            return {"user_id": user_id, "tenant_id": tenant_id, "message": "User assigned to tenant"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}

    def get_user_tenant(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get the tenant a user belongs to."""
        c = self._conn()
        try:
            row = c.execute("SELECT tenant_id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row or not row["tenant_id"]:
                return None
            return self.get_tenant(row["tenant_id"])
        except sqlite3.Error as e:
            logger.error("AuthService: get_user_tenant error: %s", e)
            return None

    def list_tenant_users(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all users in a tenant."""
        c = self._conn()
        try:
            rows = c.execute(
                "SELECT id, username, email, role, active, created_at, last_login "
                "FROM users WHERE tenant_id = ? ORDER BY id",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error("AuthService: list_tenant_users error: %s", e)
            return []
