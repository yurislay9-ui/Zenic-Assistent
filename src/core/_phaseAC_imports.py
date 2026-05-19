"""
Phase A-C imports: Observability, Events, Workflows, Exceptions.

Split from src/core/__init__.py for maintainability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Phase A: Observability ────────────────────────────────
try:
    from src.core.observability import (
        ForensicEngine,
        ForensicEntry,
        ForensicReport,
        ChainVerificationResult,
        EvidenceBundle,
        get_forensic_engine,
        SnapshotAuditEngine,
        SnapshotEntry,
        SnapshotPair,
        SnapshotDiff,
        get_snapshot_audit_engine,
        AuditLogger,
        AuditEvent,
        AuditEventType,
        AuditSeverity,
        get_audit_logger,
        HealthAggregator,
        HealthStatus,
        HealthCheckResult,
        get_health_aggregator,
        MetricsCollector,
        MetricsConfig,
        get_metrics_collector,
        TracingConfig,
        init_tracing,
        get_tracer,
        trace_span,
    )
except ImportError as exc:
    logger.warning("core: Observability import failed: %s", exc)
    ForensicEngine = None  # type: ignore[misc,assignment]
    ForensicEntry = None  # type: ignore[misc,assignment]
    ForensicReport = None  # type: ignore[misc,assignment]
    ChainVerificationResult = None  # type: ignore[misc,assignment]
    EvidenceBundle = None  # type: ignore[misc,assignment]
    get_forensic_engine = None  # type: ignore[misc,assignment]
    SnapshotAuditEngine = None  # type: ignore[misc,assignment]
    SnapshotEntry = None  # type: ignore[misc,assignment]
    SnapshotPair = None  # type: ignore[misc,assignment]
    SnapshotDiff = None  # type: ignore[misc,assignment]
    get_snapshot_audit_engine = None  # type: ignore[misc,assignment]
    AuditLogger = None  # type: ignore[misc,assignment]
    AuditEvent = None  # type: ignore[misc,assignment]
    AuditEventType = None  # type: ignore[misc,assignment]
    AuditSeverity = None  # type: ignore[misc,assignment]
    get_audit_logger = None  # type: ignore[misc,assignment]
    HealthAggregator = None  # type: ignore[misc,assignment]
    HealthStatus = None  # type: ignore[misc,assignment]
    HealthCheckResult = None  # type: ignore[misc,assignment]
    get_health_aggregator = None  # type: ignore[misc,assignment]
    MetricsCollector = None  # type: ignore[misc,assignment]
    MetricsConfig = None  # type: ignore[misc,assignment]
    get_metrics_collector = None  # type: ignore[misc,assignment]
    TracingConfig = None  # type: ignore[misc,assignment]
    init_tracing = None  # type: ignore[misc,assignment]
    get_tracer = None  # type: ignore[misc,assignment]
    trace_span = None  # type: ignore[misc,assignment]

# ── Phase B: Events ───────────────────────────────────────
try:
    from src.core.events import (
        TriggerMap,
        TriggerMapping,
        TriggerCondition,
        ConditionOperator as EventConditionOperator,
        get_trigger_map,
        # WebhookIngestionEngine removed — external API connection deleted
        EventSchemaRegistry,
        EventSchema,
        ValidationResult as EventValidationResult,
        ValidationIssue,
        IssueType,
        get_schema_registry,
        ReplayQueue,
        DeadLetterEvent,
        DeadLetterStatus,
        RetryResult,
        BatchRetryResult,
        get_replay_queue,
    )
except ImportError as exc:
    logger.warning("core: Events import failed: %s", exc)
    TriggerMap = None  # type: ignore[misc,assignment]
    TriggerMapping = None  # type: ignore[misc,assignment]
    TriggerCondition = None  # type: ignore[misc,assignment]
    EventConditionOperator = None  # type: ignore[misc,assignment]
    get_trigger_map = None  # type: ignore[misc,assignment]
    # WebhookIngestionEngine removed — external API connection deleted
    EventSchemaRegistry = None  # type: ignore[misc,assignment]
    EventSchema = None  # type: ignore[misc,assignment]
    EventValidationResult = None  # type: ignore[misc,assignment]
    ValidationIssue = None  # type: ignore[misc,assignment]
    IssueType = None  # type: ignore[misc,assignment]
    get_schema_registry = None  # type: ignore[misc,assignment]
    ReplayQueue = None  # type: ignore[misc,assignment]
    DeadLetterEvent = None  # type: ignore[misc,assignment]
    DeadLetterStatus = None  # type: ignore[misc,assignment]
    RetryResult = None  # type: ignore[misc,assignment]
    BatchRetryResult = None  # type: ignore[misc,assignment]
    get_replay_queue = None  # type: ignore[misc,assignment]

# ── Phase B: Workflows ────────────────────────────────────
try:
    from src.core.workflows import (
        DynamicChainComposer,
        ComposedChain,
        ChainStep,
        ChainStepResult,
        ChainExecutionResult,
        ChainValidationResult,
        get_chain_composer,
        ChainTemplateLibrary,
        ChainTemplate,
        TemplateStep,
        TemplateVariable,
        TemplateCategory,
        get_template_library,
        InterWorkflowHandoff,
        HandoffRule,
        HandoffResult,
        FieldMapping,
        get_inter_workflow_handoff,
        ConditionalBranching,
        BranchRule,
        BranchCondition,
        get_conditional_branching,
    )
except ImportError as exc:
    logger.warning("core: Workflows import failed: %s", exc)
    DynamicChainComposer = None  # type: ignore[misc,assignment]
    ComposedChain = None  # type: ignore[misc,assignment]
    ChainStep = None  # type: ignore[misc,assignment]
    ChainStepResult = None  # type: ignore[misc,assignment]
    ChainExecutionResult = None  # type: ignore[misc,assignment]
    ChainValidationResult = None  # type: ignore[misc,assignment]
    get_chain_composer = None  # type: ignore[misc,assignment]
    ChainTemplateLibrary = None  # type: ignore[misc,assignment]
    ChainTemplate = None  # type: ignore[misc,assignment]
    TemplateStep = None  # type: ignore[misc,assignment]
    TemplateVariable = None  # type: ignore[misc,assignment]
    TemplateCategory = None  # type: ignore[misc,assignment]
    get_template_library = None  # type: ignore[misc,assignment]
    InterWorkflowHandoff = None  # type: ignore[misc,assignment]
    HandoffRule = None  # type: ignore[misc,assignment]
    HandoffResult = None  # type: ignore[misc,assignment]
    FieldMapping = None  # type: ignore[misc,assignment]
    get_inter_workflow_handoff = None  # type: ignore[misc,assignment]
    ConditionalBranching = None  # type: ignore[misc,assignment]
    BranchRule = None  # type: ignore[misc,assignment]
    BranchCondition = None  # type: ignore[misc,assignment]
    get_conditional_branching = None  # type: ignore[misc,assignment]

# ── Phase C: Exceptions ───────────────────────────────────
try:
    from src.core.exceptions import (
        ExceptionCategory,
        ExceptionSeverity,
        ZenicException,
        ExceptionContext,
        ExceptionEngine,
        ExceptionSignal,
        ExceptionRecord,
        get_exception_engine,
        ExceptionRouter,
        RoutingRule,
        RoutingAction,
        get_exception_router,
        ExceptionAnalytics,
        ExceptionPattern,
        AnalyticsSnapshot,
        get_exception_analytics,
    )
except ImportError as exc:
    logger.warning("core: Exceptions import failed: %s", exc)
    ExceptionCategory = None  # type: ignore[misc,assignment]
    ExceptionSeverity = None  # type: ignore[misc,assignment]
    ZenicException = None  # type: ignore[misc,assignment]
    ExceptionContext = None  # type: ignore[misc,assignment]
    ExceptionEngine = None  # type: ignore[misc,assignment]
    ExceptionSignal = None  # type: ignore[misc,assignment]
    ExceptionRecord = None  # type: ignore[misc,assignment]
    get_exception_engine = None  # type: ignore[misc,assignment]
    ExceptionRouter = None  # type: ignore[misc,assignment]
    RoutingRule = None  # type: ignore[misc,assignment]
    RoutingAction = None  # type: ignore[misc,assignment]
    get_exception_router = None  # type: ignore[misc,assignment]
    ExceptionAnalytics = None  # type: ignore[misc,assignment]
    ExceptionPattern = None  # type: ignore[misc,assignment]
    AnalyticsSnapshot = None  # type: ignore[misc,assignment]
    get_exception_analytics = None  # type: ignore[misc,assignment]
