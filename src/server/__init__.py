"""
ZENIC-AGENTS v16 - Server Package

Servidor HTTP OpenAI-compatible compartido entre TUI (Textual) y Termux.
Elimina la duplicacion de ~300 lineas entre main.py y main_headless.py.

SaaS Phase 1: FastAPI server with auth, tenants, rate limiting.
"""

from src.server.http_handler import ZenicHTTPHandler
from src.server.server import ThreadedHTTPServer, get_local_ip, get_network_info, configure_handler
from src.server.rate_limiter import RateLimiter
from src.server.tenant_rate_limiter import TenantRateLimiter
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)

# Lazy imports for FastAPI (avoids hard dependency)
def get_fastapi_app():
    """Import and return the FastAPI app module. Raises ImportError if FastAPI not installed."""
    from src.server.fastapi_app import create_app, run_fastapi_server
    return create_app, run_fastapi_server

def get_auth_middleware():
    """Import and return the auth middleware module."""
    from src.server.auth_middleware import AuthContext, resolve_auth, require_auth
    return AuthContext, resolve_auth, require_auth

__all__ = [
    "ZenicHTTPHandler",
    "ThreadedHTTPServer",
    "get_local_ip",
    "get_network_info",
    "configure_handler",
    "RateLimiter",
    "TenantRateLimiter",
    "build_normal_response",
    "build_partial_reasoning_response",
    "build_error_response",
    "build_overloaded_response",
    "get_fastapi_app",
    "get_auth_middleware",
]
