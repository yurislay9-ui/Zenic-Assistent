"""
FastAPI application factory and entry-point helpers.

Provides:
- ``create_app()`` — main factory that assembles the FastAPI instance
- ``get_app()`` — lazy singleton accessor (for uvicorn)
- ``create_app_from_env()`` — env-var-based factory (for Gunicorn / Docker)
- ``run_fastapi_server()`` — convenience wrapper around uvicorn
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    os,
    time,
    threading,
    logging,
    logger,
    ZENIC_VERSION,
    ZENIC_FULL_NAME,
    _app,
)
from src.server.fastapi_parts._middleware import setup_middleware
from src.server.fastapi_parts._helpers import make_auth_dependencies
from src.server.fastapi_parts._routes_chat import register_chat_routes
from src.server.fastapi_parts._routes_agents import register_agent_routes
from src.server.fastapi_parts._routes_executors import register_executor_routes
from src.server.fastapi_parts._routes_admin import register_admin_routes
from src.server.fastapi_parts._routes_auth import register_auth_routes
from src.server.fastapi_parts._routes_sna import register_sna_routes
from src.server.fastapi_parts.htmx_routes import (
    register_dashboard_routes,
    register_sna_htmx_routes,
    register_audit_htmx_routes,
    register_billing_routes,
    register_module_routes,
    register_system_routes,
    register_inventory_routes,
    register_crm_routes,
    register_onboarding_routes,
)


# ────────────────────────────────────────────────────────────
#  Main factory
# ────────────────────────────────────────────────────────────

def create_app(
    orchestrator: Any,
    auth_service: Any = None,
    rate_limiter: Any = None,
    governor: Any = None,
    platform_tag: str = "",
) -> Any:
    """Create and configure the FastAPI application.

    Args:
        orchestrator: DAGOrchestrator or ZenicOrchestrator instance.
        auth_service: AuthService instance (optional, auth disabled if None).
        rate_limiter: TenantRateLimiter or RateLimiter instance.
        governor: ResourceGovernor instance (optional).
        platform_tag: Platform identifier (e.g. 'termux-proot').

    Returns:
        FastAPI application instance.
    """
    try:
        from fastapi import FastAPI
    except ImportError:
        raise ImportError(
            "FastAPI is required for the SaaS server. "
            "Install with: pip install fastapi uvicorn"
        )

    start_time = time.time()

    app = FastAPI(
        title=f"{ZENIC_FULL_NAME}",
        description="Local Surgical AI Engine — OpenAI-Compatible API",
        version=ZENIC_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware & observability ───────────────────────────
    setup_middleware(
        app,
        orchestrator=orchestrator,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
        start_time=start_time,
    )

    # ── App state ───────────────────────────────────────────
    app.state.orchestrator = orchestrator
    app.state.auth_service = auth_service
    app.state.rate_limiter = rate_limiter
    app.state.governor = governor
    app.state.platform_tag = platform_tag
    app.state.start_time = start_time
    app.state.request_count = 0
    app.state._request_count_lock = threading.Lock()  # noqa: SLF001

    # ── Auth dependencies ───────────────────────────────────
    _get_auth_ctx, require_auth_dep = make_auth_dependencies(auth_service)

    # ── Routes ──────────────────────────────────────────────
    register_chat_routes(app, orchestrator=orchestrator, governor=governor)
    register_agent_routes(app, orchestrator=orchestrator)
    register_executor_routes(app, auth_service=auth_service, require_auth_dep=require_auth_dep)
    register_admin_routes(
        app,
        orchestrator=orchestrator,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
        platform_tag=platform_tag,
        start_time=start_time,
        require_auth_dep=require_auth_dep,
    )

    # Auth + tenant routes (only when auth_service is configured)
    if auth_service is not None:
        register_auth_routes(app, auth_service=auth_service, require_auth_dep=require_auth_dep)

    # SNA routes (Phase 4)
    register_sna_routes(app, auth_service=auth_service, require_auth_dep=require_auth_dep)

    # ── HTMX + Jinja2 routes (Phase 7) ────────────────────
    try:
        # Static files serving
        from fastapi.staticfiles import StaticFiles
        import os as _os
        _static_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(__file__)), "static"
        )
        if _os.path.isdir(_static_dir):
            app.mount("/static", StaticFiles(directory=_static_dir), name="static")

        # Register all HTMX route groups
        register_dashboard_routes(app)
        register_sna_htmx_routes(app)
        register_audit_htmx_routes(app)
        register_billing_routes(app)
        register_module_routes(app)
        register_system_routes(app)
        register_inventory_routes(app)
        register_crm_routes(app)
        register_onboarding_routes(app)

        logger.info("HTMX + Jinja2 frontend routes registered (Phase 7 + Enhanced)")
    except Exception as e:
        logger.warning("HTMX routes not registered: %s (non-critical, API still works)", e)

    return app


# ────────────────────────────────────────────────────────────
#  Lazy singleton accessor
# ────────────────────────────────────────────────────────────

def get_app() -> Any:
    """Get or lazily create the FastAPI app (for uvicorn)."""
    import src.server.fastapi_parts._imports as _mod

    return _mod._app  # noqa: SLF001


# ────────────────────────────────────────────────────────────
#  Env-var-based factory (Gunicorn / Docker)
# ────────────────────────────────────────────────────────────

def create_app_from_env() -> Any:
    """Factory function for Gunicorn + Docker deployment.

    Reads environment variables to configure and create the FastAPI app
    without requiring explicit constructor arguments.

    Environment variables:
        ZENIC_ENV: 'production' or 'development' (default: development)
        ZENIC_AUTH_ENABLED: 'true' to enable auth (default: false in dev)
        ZENIC_AUTH_SECRET: JWT secret (required if auth enabled)
        ZENIC_RAM_LIMIT_MB: RAM limit in MB (default: 4096)
        DATABASE_URL: PostgreSQL or SQLite connection string
    """
    import src.server.fastapi_parts._imports as _mod

    # Load .env if present
    try:
        from src.core.env_loader import load_env
        load_env()
    except Exception:
        pass

    # Initialize ResourceGovernor
    ram_limit = int(os.environ.get("ZENIC_RAM_LIMIT_MB", "4096"))
    governor: Optional[Any] = None
    try:
        from src.core.shared.resource_governor import (
            tune_gc_for_arm,
            set_process_priority_low,
            limit_open_files,
            init_governor,
        )
        tune_gc_for_arm()
        set_process_priority_low()
        limit_open_files()
        governor = init_governor(ram_limit_mb=ram_limit)
    except Exception as e:
        logger.warning("ResourceGovernor init failed: %s", e)

    # Initialize database
    from src.core.shared.db_adapters import get_db, is_postgresql

    if is_postgresql():
        logger.info("Production mode: PostgreSQL backend selected")
    else:
        try:
            from src.core.shared.db_initializer import initialize_databases
            initialize_databases()
        except Exception as e:
            logger.warning("Database init failed: %s", e)

    # Create orchestrator
    orchestrator: Optional[Any] = None
    try:
        from src.core.orchestrator import ZenicOrchestrator as DAGOrchestrator  # Migrated
        orchestrator = DAGOrchestrator()
    except ImportError:
        try:
            from src.core.orchestrator import ZenicOrchestrator
            orchestrator = ZenicOrchestrator()
        except ImportError:
            logger.warning("No orchestrator available — AI endpoints will fail")

    # Connect governor to model manager
    if governor and hasattr(orchestrator, "_model_mgr"):
        governor.set_model_manager(orchestrator._model_mgr)  # noqa: SLF001

    # Auth service
    auth_service: Optional[Any] = None
    auth_enabled = os.environ.get("ZENIC_AUTH_ENABLED", "").lower() in ("true", "1", "yes")
    if auth_enabled or os.environ.get("ZENIC_ENV") == "production":
        try:
            from src.core.auth_service import AuthService
            auth_service = AuthService()
            auth_service.ensure_admin()
            logger.info("AuthService: initialized with tenant support")
        except Exception as e:
            logger.warning("AuthService init failed: %s", e)

    # Rate limiter
    _rl_rpm = int(os.environ.get("ZENIC_RATE_LIMIT_RPM", str(max(1, ram_limit // 64))))
    _rl_burst = int(os.environ.get("ZENIC_RATE_LIMIT_BURST", "20"))
    _rl_concurrent = int(os.environ.get("ZENIC_RATE_LIMIT_CONCURRENT", "60"))
    rate_limiter: Optional[Any] = None
    if auth_service is not None:
        try:
            from src.server.tenant_rate_limiter import TenantRateLimiter
            rate_limiter = TenantRateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
                default_user_rpm=_rl_rpm,
                default_user_burst=_rl_burst,
            )
        except ImportError:
            from src.server.rate_limiter import RateLimiter
            rate_limiter = RateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
            )
    else:
        try:
            from src.server.rate_limiter import RateLimiter
            rate_limiter = RateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
            )
        except ImportError:
            rate_limiter = None

    # Platform tag
    platform_tag = "production" if os.environ.get("ZENIC_ENV") == "production" else "development"

    # Create and return the FastAPI app
    _app_instance = create_app(
        orchestrator=orchestrator,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
        platform_tag=platform_tag,
    )
    _mod._app = _app_instance  # noqa: SLF001
    return _app_instance


# ────────────────────────────────────────────────────────────
#  Convenience uvicorn runner
# ────────────────────────────────────────────────────────────

def run_fastapi_server(
    orchestrator: Any,
    host: str = "0.0.0.0",
    port: int = 5000,
    auth_service: Any = None,
    rate_limiter: Any = None,
    governor: Any = None,
    platform_tag: str = "",
) -> None:
    """Start the FastAPI server using uvicorn."""
    import uvicorn
    import src.server.fastapi_parts._imports as _mod

    _mod._app = create_app(  # noqa: SLF001
        orchestrator=orchestrator,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
        platform_tag=platform_tag,
    )
    uvicorn.run(_mod._app, host=host, port=port, log_level="info")  # noqa: SLF001
