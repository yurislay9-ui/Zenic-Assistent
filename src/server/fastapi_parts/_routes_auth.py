"""
Auth and tenant endpoints — /v1/auth/*, /v1/tenants/*.

Split from _routes_admin.py to keep each module under 400 lines.
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    logging,
    logger,
    AuthContext,
    _AUDIT_AVAILABLE,
    AuditEventType,
)


def register_auth_routes(
    app: Any,
    *,
    auth_service: Any,
    require_auth_dep: Any,
) -> None:
    """Register /v1/auth/* and /v1/tenants/* routes when auth_service is available."""

    from fastapi import Request, HTTPException, Depends

    # ════════════════════════════════════════════════════════
    #  AUTH ENDPOINTS (public registration/login)
    # ════════════════════════════════════════════════════════

    @app.post("/v1/auth/register")
    async def auth_register(request: Request):
        """Register a new user."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        result = auth_service.register_user(
            username=body.get("username", ""),
            email=body.get("email", ""),
            password=body.get("password", ""),
            role="user",
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.post("/v1/auth/login")
    async def auth_login(request: Request):
        """Authenticate user and return tokens."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        result = auth_service.login_user(
            username=body.get("username", ""),
            password=body.get("password", ""),
        )
        if "error" in result:
            raise HTTPException(status_code=401, detail=result["error"])
        return result

    @app.post("/v1/auth/refresh")
    async def auth_refresh(request: Request):
        """Refresh access token."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        result = auth_service.refresh_access_token(body.get("refresh_token", ""))
        if "error" in result:
            raise HTTPException(status_code=401, detail=result["error"])
        return result

    @app.get("/v1/auth/me")
    async def auth_me(auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get current user info."""
        user = auth_service.get_user(auth_ctx.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @app.post("/v1/auth/api-keys")
    async def create_api_key(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Create an API key for the current user."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        result = auth_service.create_api_key(
            user_id=auth_ctx.user_id,
            name=body.get("name", "default"),
            permissions=body.get("permissions"),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/v1/auth/api-keys")
    async def list_api_keys(auth_ctx: AuthContext = Depends(require_auth_dep)):
        """List API keys for the current user."""
        return auth_service.list_api_keys(auth_ctx.user_id)

    # ── Tenant endpoints (admin/manager only) ──────────────
    _register_tenant_routes(app, auth_service=auth_service, require_auth_dep=require_auth_dep)


def _register_tenant_routes(
    app: Any,
    *,
    auth_service: Any,
    require_auth_dep: Any,
) -> None:
    """Register /v1/tenants/* routes."""

    from fastapi import Request, HTTPException, Depends

    @app.get("/v1/tenants")
    async def list_tenants(auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager or admin required")
        return auth_service.list_tenants()

    @app.post("/v1/tenants")
    async def create_tenant(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("admin"):
            raise HTTPException(status_code=403, detail="Admin required")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        result = auth_service.create_tenant(
            name=body.get("name", ""), plan=body.get("plan", "free"), config=body.get("config"),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.get("/v1/tenants/{tenant_id}")
    async def get_tenant(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager or admin required")
        tenant = auth_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant

    @app.post("/v1/tenants/{tenant_id}/assign/{user_id}")
    async def assign_user(tenant_id: str, user_id: int, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("admin"):
            raise HTTPException(status_code=403, detail="Admin required")
        result = auth_service.assign_user_to_tenant(user_id, tenant_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.patch("/v1/tenants/{tenant_id}")
    async def update_tenant(tenant_id: str, request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("admin"):
            raise HTTPException(status_code=403, detail="Admin required")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        result = auth_service.update_tenant(
            tenant_id, name=body.get("name"), plan=body.get("plan"), config=body.get("config"),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app.delete("/v1/tenants/{tenant_id}")
    async def delete_tenant(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("admin"):
            raise HTTPException(status_code=403, detail="Admin required")
        if not hasattr(auth_service, "deprovision_tenant"):
            raise HTTPException(status_code=501, detail="Deprovision not available")
        result = auth_service.deprovision_tenant(tenant_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.get("/v1/tenants/{tenant_id}/usage")
    async def get_tenant_usage(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager or admin required")
        usage = auth_service.get_tenant_usage(tenant_id)
        quota = (
            auth_service.check_tenant_quota(tenant_id)
            if hasattr(auth_service, "check_tenant_quota")
            else None
        )
        storage = (
            auth_service.check_storage_quota(tenant_id)
            if hasattr(auth_service, "check_storage_quota")
            else None
        )
        return {"tenant_id": tenant_id, "usage": usage, "quota": quota, "storage": storage}

    @app.get("/v1/tenants/{tenant_id}/features")
    async def get_tenant_features_api(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager or admin required")
        features = (
            auth_service.get_tenant_features(tenant_id) if hasattr(auth_service, "get_tenant_features") else []
        )
        return {"tenant_id": tenant_id, "features": features}
