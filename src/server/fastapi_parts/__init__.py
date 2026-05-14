"""
FastAPI application sub-modules.

Re-exports the public API of the refactored ``fastapi_app`` module so that
existing ``from src.server.fastapi_app import …`` statements continue to work.
"""

from src.server.fastapi_parts._app_factory import (
    create_app,
    get_app,
    create_app_from_env,
    run_fastapi_server,
)
from src.server.fastapi_parts._helpers import (
    _run_orchestrator,
    _basic_sse_generator,
    make_auth_dependencies,
)
from src.server.fastapi_parts._imports import (
    _TRACING_AVAILABLE,
    _METRICS_AVAILABLE,
    _AUDIT_AVAILABLE,
    _HEALTH_AVAILABLE,
    _SECURITY_AVAILABLE,
    _OPEN_DESIGN_AVAILABLE,
    _app,
    _ORCH_RETRY,
    _orch_breaker,
)

__all__ = [
    # Factory functions
    "create_app",
    "get_app",
    "create_app_from_env",
    "run_fastapi_server",
    # Helpers
    "_run_orchestrator",
    "_basic_sse_generator",
    "make_auth_dependencies",
    # Availability flags
    "_TRACING_AVAILABLE",
    "_METRICS_AVAILABLE",
    "_AUDIT_AVAILABLE",
    "_HEALTH_AVAILABLE",
    "_SECURITY_AVAILABLE",
    "_OPEN_DESIGN_AVAILABLE",
    # Module-level state
    "_app",
    "_ORCH_RETRY",
    "_orch_breaker",
]
