"""
Shared imports and constants for the FastAPI application sub-modules.

Centralizes all imports, availability flags, and reusable configuration
objects so that every route / middleware module can import from here
instead of duplicating import blocks.
"""

import json
import time
import logging
import uuid
import threading
import asyncio
import os
from typing import Any, Dict, List, Optional

# ── Project imports ────────────────────────────────────────
from src.core.shared._version import ZENIC_VERSION, ZENIC_VERSION_STR, ZENIC_FULL_NAME
from src.core.patterns.resilience.retry import RetryConfig, with_retry
from src.core.patterns.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from src.server.auth_middleware import AuthContext, resolve_auth, require_auth
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
    build_artifact_response,
)
from src.core.auth_parts._tenant_mixin import PLAN_DEFINITIONS
from src.core.tenant._context import (
    TenantContext,
    set_current_tenant,
    clear_current_tenant,
    get_current_tenant,
)
from src.core.tenant._feature_gate import require_feature, FeatureNotAvailableError

# ── Phase 5: Observability & Security (optional) ──────────
try:
    from src.core.observability.tracing import (
        TracingConfig, init_tracing, trace_span, get_current_trace_id,
    )
    _TRACING_AVAILABLE = True
except ImportError:
    _TRACING_AVAILABLE = False

try:
    from src.core.observability.metrics import (
        MetricsCollector, MetricsConfig, get_metrics_collector, metrics_middleware,
    )
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

try:
    from src.core.observability.audit import (
        AuditLogger, AuditEvent, AuditEventType, AuditSeverity, get_audit_logger,
    )
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

try:
    from src.core.observability.health import (
        HealthAggregator, HealthStatus, HealthCheckResult, get_health_aggregator,
        check_orchestrator, check_auth_db, check_resources, check_disk_space,
        check_coordination_backend,
    )
    _HEALTH_AVAILABLE = True
except ImportError:
    _HEALTH_AVAILABLE = False

try:
    from src.server.security_middleware import (
        SecurityConfig, InputSanitizer, create_security_middleware, TokenBlacklist,
    )
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False

# ── Open Design Integration (optional) ────────────────────
try:
    from src.core.open_design import (
        OpenDesignDetector, OpenDesignConfig, get_open_design_config,
        SSEStreamer, create_sse_response,
    )
    _OPEN_DESIGN_AVAILABLE = True
except ImportError:
    _OPEN_DESIGN_AVAILABLE = False

# ── Logger ─────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Retry / Circuit-Breaker configs ────────────────────────
_ORCH_RETRY = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=5.0,
    backoff_strategy="exponential",
    jitter=True,
    retryable_exceptions=(Exception,),
)

_orch_breaker = CircuitBreaker(
    name="orchestrator",
    failure_threshold=10,
    recovery_timeout=60.0,
)

# ── FastAPI lazy singleton ─────────────────────────────────
_app: Optional[Any] = None
