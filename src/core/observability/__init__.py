"""
ZENIC-AGENTS v16 - Observability Module (Phase 5)

Comprehensive observability stack:
- OpenTelemetry-compatible tracing with Jaeger export
- Prometheus metrics with standard client library
- Structured audit logging with trace correlation
- Health check aggregation for all subsystems

All components are optional — graceful degradation when
dependencies are not installed (e.g. on Termux/ARM).
"""

from .tracing import (
    TracingConfig,
    init_tracing,
    get_tracer,
    trace_span,
    get_current_trace_id,
    get_current_span_id,
    inject_trace_context,
    extract_trace_context,
)
from .metrics import (
    MetricsCollector,
    MetricsConfig,
    get_metrics_collector,
    metrics_middleware,
)
from .audit import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    get_audit_logger,
)
from .health import (
    HealthAggregator,
    HealthStatus,
    HealthCheckResult,
    get_health_aggregator,
    check_orchestrator,
    check_auth_db,
    check_resources,
    check_disk_space,
    check_coordination_backend,
    check_redis,
)
from .forensic import (
    ForensicEngine,
    ForensicEntry,
    ForensicReport,
    ChainVerificationResult,
    EvidenceBundle,
    get_forensic_engine,
    reset_forensic_engine,
)
from .snapshot_audit import (
    SnapshotAuditEngine,
    SnapshotEntry,
    SnapshotPair,
    SnapshotDiff,
    get_snapshot_audit_engine,
    reset_snapshot_audit_engine,
)

__all__ = [
    # Tracing
    "TracingConfig", "init_tracing", "get_tracer", "trace_span",
    "get_current_trace_id", "get_current_span_id",
    "inject_trace_context", "extract_trace_context",
    # Metrics
    "MetricsCollector", "MetricsConfig", "get_metrics_collector", "metrics_middleware",
    # Audit
    "AuditLogger", "AuditEvent", "AuditEventType", "AuditSeverity", "get_audit_logger",
    # Health
    "HealthAggregator", "HealthStatus", "HealthCheckResult",
    "get_health_aggregator",
    "check_orchestrator", "check_auth_db", "check_resources",
    "check_disk_space", "check_coordination_backend", "check_redis",
    # Forensic
    "ForensicEngine", "ForensicEntry", "ForensicReport",
    "ChainVerificationResult", "EvidenceBundle",
    "get_forensic_engine", "reset_forensic_engine",
    # Snapshot Audit
    "SnapshotAuditEngine", "SnapshotEntry", "SnapshotPair", "SnapshotDiff",
    "get_snapshot_audit_engine", "reset_snapshot_audit_engine",
]
