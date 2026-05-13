"""
RBAC and FastAPI integration mixin for AuthService.

Phase 6: Granular multi-role system with per-action permissions.
Roles: admin, gerente, operador, viewer (plus backward-compat aliases).
"""

from ._imports import (
    logger, ROLE_HIERARCHY, ROLE_PERMISSIONS, ACTION_PERMISSION_MAP,
    HAS_FASTAPI, Depends, HTTPException, _security,
)
from typing import Any, Dict, List, Optional, Set


class RbacMixin:
    """RBAC and FastAPI integration for AuthService.

    Phase 6 adds:
    - Granular per-action permissions (create_invoice, approve_financial, etc.)
    - check_action_permission() for action-level access control
    - role resolution with backward compatibility (user→operador, manager→gerente)
    - approval authority mapping for chain-of-approval system
    """

    # ── Core permission checks ─────────────────────────────

    def check_permission(self, user_id: int, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.get_user_permissions(user_id)

    def check_role(self, user_id: int, minimum_role: str) -> bool:
        """Check if user meets minimum role level."""
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return False
        return ROLE_HIERARCHY.get(user.get("role", ""), -1) >= ROLE_HIERARCHY.get(minimum_role, -1)

    def get_user_permissions(self, user_id: int) -> Set[str]:
        """Get all permissions for user based on their role."""
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return set()
        return ROLE_PERMISSIONS.get(user.get("role", "viewer"), set())

    # ── Phase 6: Action-level permission checks ────────────

    def check_action_permission(
        self, user_id: int, action: str, context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check if user can perform a specific action.

        Returns a dict with:
        - allowed: bool
        - reason: str (empty if allowed)
        - required_permission: str
        - user_role: str
        - missing_permissions: set
        """
        required_perm = ACTION_PERMISSION_MAP.get(action, "write")
        user_perms = self.get_user_permissions(user_id)
        user = self.get_user(user_id)
        role = user.get("role", "viewer") if user else "viewer"

        if required_perm in user_perms:
            return {
                "allowed": True,
                "reason": "",
                "required_permission": required_perm,
                "user_role": role,
                "missing_permissions": set(),
            }

        missing = set()
        if required_perm not in user_perms:
            missing.add(required_perm)

        return {
            "allowed": False,
            "reason": f"Role '{role}' lacks permission '{required_perm}' for action '{action}'",
            "required_permission": required_perm,
            "user_role": role,
            "missing_permissions": missing,
        }

    def get_approval_authority(self, action: str) -> str:
        """Get the minimum role that can approve an action.

        Maps actions to their approval authority:
        - Financial actions → gerente
        - Destructive actions → admin
        - System config → admin
        - Default → gerente
        """
        approval_map = {
            "approve_financial": "gerente",
            "create_payment": "gerente",
            "refund": "admin",
            "approve_destructive": "admin",
            "delete_record": "gerente",
            "change_config": "admin",
            "manage_roles": "admin",
            "manage_system": "admin",
            "manage_blueprints": "admin",
        }
        return approval_map.get(action, "gerente")

    def can_user_approve(self, approver_id: int, action: str) -> bool:
        """Check if a user has authority to approve a given action."""
        required_role = self.get_approval_authority(action)
        return self.check_role(approver_id, required_role)

    # ── Role resolution ────────────────────────────────────

    def resolve_role(self, role: str) -> str:
        """Resolve backward-compatible role names to Phase 6 names.

        'user' → 'operador', 'manager' → 'gerente'
        """
        alias_map = {"user": "operador", "manager": "gerente"}
        return alias_map.get(role, role)

    def get_role_info(self, role: str) -> Dict[str, Any]:
        """Get full info about a role: level, permissions, display name."""
        resolved = self.resolve_role(role)
        level = ROLE_HIERARCHY.get(resolved, -1)
        perms = ROLE_PERMISSIONS.get(resolved, set())
        display_names = {
            "admin": "Administrador",
            "gerente": "Gerente",
            "operador": "Operador",
            "viewer": "Visualizador",
        }
        return {
            "role": resolved,
            "level": level,
            "permissions": sorted(perms),
            "display_name": display_names.get(resolved, resolved),
            "can_approve_financial": "approve_financial" in perms,
            "can_approve_destructive": "approve_destructive" in perms,
            "can_manage_users": "manage_users" in perms,
        }

    def list_available_roles(self) -> List[Dict[str, Any]]:
        """List all available roles with their info."""
        core_roles = ["viewer", "operador", "gerente", "admin"]
        return [self.get_role_info(r) for r in core_roles]

    # ── FastAPI dependency factories ────────────────────────

    def require_permission(self, permission: str):
        """FastAPI dependency factory requiring a specific permission."""
        auth = self
        async def _check(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            if not auth.check_permission(uid, permission):
                raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
            return {"user_id": uid, "role": payload.get("role", "operador"),
                    "permissions": list(auth.get_user_permissions(uid))}
        return _check

    def require_role(self, minimum_role: str):
        """FastAPI dependency factory requiring minimum role."""
        auth = self
        async def _check(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            if not auth.check_role(uid, minimum_role):
                raise HTTPException(status_code=403, detail=f"Role '{minimum_role}' or higher required")
            return {"user_id": uid, "role": payload.get("role", "operador"),
                    "permissions": list(auth.get_user_permissions(uid))}
        return _check

    def require_action_permission(self, action: str):
        """FastAPI dependency factory requiring action-specific permission."""
        auth = self
        async def _check(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            result = auth.check_action_permission(uid, action)
            if not result["allowed"]:
                raise HTTPException(status_code=403, detail=result["reason"])
            return {"user_id": uid, "role": payload.get("role", "operador"),
                    "permissions": list(auth.get_user_permissions(uid)),
                    "action": action}
        return _check

    def get_auth_dependencies(self) -> dict:
        """Returns FastAPI dependency functions for auth."""
        if not HAS_FASTAPI:
            return {"error": "FastAPI not available"}
        auth = self

        async def get_current_user(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            user = auth.get_user(uid)
            if not user or not user.get("active"):
                raise HTTPException(status_code=401, detail="User not found or deactivated")
            return {"user_id": uid, "username": user.get("username", ""),
                    "role": user.get("role", "viewer"), "permissions": list(auth.get_user_permissions(uid))}

        async def require_admin(user=Depends(get_current_user)) -> dict:
            if user.get("role") not in ("admin",):
                raise HTTPException(status_code=403, detail="Admin access required")
            return user

        async def require_gerente(user=Depends(get_current_user)) -> dict:
            if ROLE_HIERARCHY.get(user.get("role", ""), -1) < ROLE_HIERARCHY.get("gerente", -1):
                raise HTTPException(status_code=403, detail="Gerente or admin access required")
            return user

        return {
            "get_current_user": get_current_user,
            "require_admin": require_admin,
            "require_gerente": require_gerente,
            "require_manager": require_gerente,
            "require_permission": lambda perm: auth.require_permission(perm),
            "require_action": lambda action: auth.require_action_permission(action),
        }

    def protect_endpoint(self, minimum_role: str = "operador"):
        """Decorator to protect a FastAPI endpoint by role."""
        if not HAS_FASTAPI:
            return lambda f: f
        auth = self

        def decorator(func):
            async def wrapper(*args, **kwargs):
                request = kwargs.get("request")
                if not request:
                    raise HTTPException(status_code=401, detail="No request object found")
                auth_hdr = request.headers.get("Authorization", "")
                if not auth_hdr.startswith("Bearer "):
                    raise HTTPException(status_code=401, detail="Bearer token required",
                                        headers={"WWW-Authenticate": "Bearer"})
                payload = auth.verify_token(auth_hdr[7:], "access")
                if "error" in payload:
                    raise HTTPException(status_code=401, detail=payload["error"])
                uid = int(payload["sub"])
                if not auth.check_role(uid, minimum_role):
                    raise HTTPException(status_code=403, detail=f"Role '{minimum_role}' or higher required")
                kwargs["auth_user_id"] = uid
                kwargs["auth_role"] = payload.get("role", "viewer")
                return await func(*args, **kwargs)
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        return decorator
