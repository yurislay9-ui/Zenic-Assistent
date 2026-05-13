"""
ZENIC-AGENTS v16 - FastAPI Application (thin facade)

This module re-exports everything from ``src.server.fastapi_parts`` so that
existing imports like ``from src.server.fastapi_app import create_app``
continue to work without any changes.

The actual implementation lives in:
    src/server/fastapi_parts/
        __init__.py          — package re-exports
        _imports.py          — shared imports and constants
        _helpers.py          — SSE streaming, orchestrator runner, tenant builder
        _middleware.py       — CORS, security, metrics, rate-limit middleware
        _routes_chat.py      — /v1/chat/completions
        _routes_agents.py    — /v1/generate/*, /v1/think, /v1/reason, /v1/chain/*
        _routes_executors.py — /v1/actions/*, /v1/executors, /v1/audit, Phase 4
        _routes_admin.py     — /health, /v1/models, auth, tenants, audit events
        _app_factory.py      — create_app(), create_app_from_env(), run_fastapi_server()
"""

from src.server.fastapi_parts import (  # noqa: F401 — re-exports for backward compat
    create_app,
    get_app,
    create_app_from_env,
    run_fastapi_server,
    _run_orchestrator,
    _basic_sse_generator,
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
