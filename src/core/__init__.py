"""
Zenic-Agents Asistente - Core Package

Phase 6: Approval, Defense, License, Degraded Mode
Phase A: Enriched Audit, Forensic (Merkle), Impact Preview, Policy Engine, Rollback
Phase B: Event-driven Actions (TriggerMap, Webhook, Schema, Replay), Workflows (Chain, Templates, Handoff, Branch)
Phase C: Dry-run/Simulation, Exception Engine, Smart Approvals (Adaptive, Risk Routing, Delegation, Batch)
Phase D: Autopilot by Objectives, ROI Dashboard
Phase E: Knowledge Graph, Conversational Memory v2, Self-Learning Loop
Phase F: Plugin SDK, Policy-as-Code, Risk Prediction (Blast Radius), Chaos Engineering
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Phase 6: Approval System ──────────────────────────────
try:
    from src.core.approval import (
        ApprovalChain,
        ApprovalRequest,
        ApprovalResult,
        ApprovalStatus,
        ApprovalPriority,
        WorkflowEngine,
        WorkflowDefinition,
        WorkflowStep,
        get_approval_chain,
        get_workflow_engine,
    )
except ImportError as exc:
    logger.warning("core: Approval import failed: %s", exc)
    ApprovalChain = None  # type: ignore[misc,assignment]
    ApprovalRequest = None  # type: ignore[misc,assignment]
    ApprovalResult = None  # type: ignore[misc,assignment]
    ApprovalStatus = None  # type: ignore[misc,assignment]
    ApprovalPriority = None  # type: ignore[misc,assignment]
    WorkflowEngine = None  # type: ignore[misc,assignment]
    WorkflowDefinition = None  # type: ignore[misc,assignment]
    WorkflowStep = None  # type: ignore[misc,assignment]
    get_approval_chain = None  # type: ignore[misc,assignment]
    get_workflow_engine = None  # type: ignore[misc,assignment]

# ── Phase 6: Defense in Depth ────────────────────────────
try:
    from src.core.defense import (
        AntiTamperingLayer,
        TamperSeverity,
        BinaryHardeningLayer,
        HardeningLevel,
        EncryptionManager,
        EncryptionLevel,
        IntegrityVerifier,
        IntegrityStatus,
        ServerSecretsLayer,
        SecretType,
        DefenseManager,
        get_defense_manager,
    )
except ImportError as exc:
    logger.warning("core: Defense import failed: %s", exc)
    AntiTamperingLayer = None  # type: ignore[misc,assignment]
    TamperSeverity = None  # type: ignore[misc,assignment]
    BinaryHardeningLayer = None  # type: ignore[misc,assignment]
    HardeningLevel = None  # type: ignore[misc,assignment]
    EncryptionManager = None  # type: ignore[misc,assignment]
    EncryptionLevel = None  # type: ignore[misc,assignment]
    IntegrityVerifier = None  # type: ignore[misc,assignment]
    IntegrityStatus = None  # type: ignore[misc,assignment]
    ServerSecretsLayer = None  # type: ignore[misc,assignment]
    SecretType = None  # type: ignore[misc,assignment]
    DefenseManager = None  # type: ignore[misc,assignment]
    get_defense_manager = None  # type: ignore[misc,assignment]

# ── Phase 6: Cryptographic Licensing ─────────────────────
try:
    from src.core.license import (
        LicenseManager,
        LicenseTier,
        LicenseStatus,
        LicenseInfo,
        LicenseVerificationResult,
        KillSwitchStatus,
        HardwareBindingStrength,
        get_license_manager,
    )
except ImportError as exc:
    logger.warning("core: License import failed: %s", exc)
    LicenseManager = None  # type: ignore[misc,assignment]
    LicenseTier = None  # type: ignore[misc,assignment]
    LicenseStatus = None  # type: ignore[misc,assignment]
    LicenseInfo = None  # type: ignore[misc,assignment]
    LicenseVerificationResult = None  # type: ignore[misc,assignment]
    KillSwitchStatus = None  # type: ignore[misc,assignment]
    HardwareBindingStrength = None  # type: ignore[misc,assignment]
    get_license_manager = None  # type: ignore[misc,assignment]

# ── Phase 6: Degraded Mode / Paralysis ───────────────────
try:
    from src.core.degraded_mode import (
        DegradedModeManager,
        SystemMode,
        ModeCapabilities,
        ModeTransition,
        get_degraded_mode_manager,
    )
except ImportError as exc:
    logger.warning("core: DegradedMode import failed: %s", exc)
    DegradedModeManager = None  # type: ignore[misc,assignment]
    SystemMode = None  # type: ignore[misc,assignment]
    ModeCapabilities = None  # type: ignore[misc,assignment]
    ModeTransition = None  # type: ignore[misc,assignment]
    get_degraded_mode_manager = None  # type: ignore[misc,assignment]

# ── Phase 6: Integration ─────────────────────────────────
try:
    from src.core.phase6_init import initialize_phase6, get_phase6_status
except ImportError as exc:
    logger.warning("core: phase6_init import failed: %s", exc)
    initialize_phase6 = None  # type: ignore[misc,assignment]
    get_phase6_status = None  # type: ignore[misc,assignment]

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

# ── Phase D: Autopilot ────────────────────────────────────
try:
    from src.core.autopilot import (
        Objective,
        ObjectiveStatus,
        ObjectivePriority,
        ObjectiveTarget,
        get_objective_store,
        KPITracker,
        KPIMeasurement,
        KPITrend,
        get_kpi_tracker,
        AutopilotPlanner,
        PlannedAction,
        PlanStep,
        get_autopilot_planner,
        ClosedLoopFeedback,
        FeedbackCycle,
        FeedbackAction,
        get_closed_loop_feedback,
        AutonomyLevel,
        AutonomyConfig,
        get_autonomy_config,
        AutopilotEngine,
        AutopilotStatus,
        get_autopilot_engine,
    )
except ImportError as exc:
    logger.warning("core: Autopilot import failed: %s", exc)
    Objective = None  # type: ignore[misc,assignment]
    ObjectiveStatus = None  # type: ignore[misc,assignment]
    ObjectivePriority = None  # type: ignore[misc,assignment]
    ObjectiveTarget = None  # type: ignore[misc,assignment]
    get_objective_store = None  # type: ignore[misc,assignment]
    KPITracker = None  # type: ignore[misc,assignment]
    KPIMeasurement = None  # type: ignore[misc,assignment]
    KPITrend = None  # type: ignore[misc,assignment]
    get_kpi_tracker = None  # type: ignore[misc,assignment]
    AutopilotPlanner = None  # type: ignore[misc,assignment]
    PlannedAction = None  # type: ignore[misc,assignment]
    PlanStep = None  # type: ignore[misc,assignment]
    get_autopilot_planner = None  # type: ignore[misc,assignment]
    ClosedLoopFeedback = None  # type: ignore[misc,assignment]
    FeedbackCycle = None  # type: ignore[misc,assignment]
    FeedbackAction = None  # type: ignore[misc,assignment]
    get_closed_loop_feedback = None  # type: ignore[misc,assignment]
    AutonomyLevel = None  # type: ignore[misc,assignment]
    AutonomyConfig = None  # type: ignore[misc,assignment]
    get_autonomy_config = None  # type: ignore[misc,assignment]
    AutopilotEngine = None  # type: ignore[misc,assignment]
    AutopilotStatus = None  # type: ignore[misc,assignment]
    get_autopilot_engine = None  # type: ignore[misc,assignment]

# ── Phase D: ROI ──────────────────────────────────────────
try:
    from src.core.roi import (
        CostAccumulator,
        CostCategory,
        CostEntry,
        get_cost_accumulator,
        ValueTracker,
        ValueCategory,
        ValueEntry,
        get_value_tracker,
        ImpactScorer,
        ImpactScore,
        get_impact_scorer,
        ROIDashboardData,
        DashboardWidget,
        TrendPoint,
        get_roi_dashboard_data,
    )
except ImportError as exc:
    logger.warning("core: ROI import failed: %s", exc)
    CostAccumulator = None  # type: ignore[misc,assignment]
    CostCategory = None  # type: ignore[misc,assignment]
    CostEntry = None  # type: ignore[misc,assignment]
    get_cost_accumulator = None  # type: ignore[misc,assignment]
    ValueTracker = None  # type: ignore[misc,assignment]
    ValueCategory = None  # type: ignore[misc,assignment]
    ValueEntry = None  # type: ignore[misc,assignment]
    get_value_tracker = None  # type: ignore[misc,assignment]
    ImpactScorer = None  # type: ignore[misc,assignment]
    ImpactScore = None  # type: ignore[misc,assignment]
    get_impact_scorer = None  # type: ignore[misc,assignment]
    ROIDashboardData = None  # type: ignore[misc,assignment]
    DashboardWidget = None  # type: ignore[misc,assignment]
    TrendPoint = None  # type: ignore[misc,assignment]
    get_roi_dashboard_data = None  # type: ignore[misc,assignment]

# ── Phase E1: Knowledge Graph ─────────────────────────────
try:
    from src.core.knowledge import (
        KnowledgeNode,
        KnowledgeEdge,
        KnowledgeQuery,
        KnowledgeSearchResult,
        GraphDomain,
        KnowledgeGraphEngine,
        get_knowledge_graph,
        reset_knowledge_graph,
        CrossAgentKnowledgeBus,
        get_cross_agent_bus,
        reset_cross_agent_bus,
    )
except ImportError as exc:
    logger.warning("core: Knowledge import failed: %s", exc)
    KnowledgeNode = None  # type: ignore[misc,assignment]
    KnowledgeEdge = None  # type: ignore[misc,assignment]
    KnowledgeQuery = None  # type: ignore[misc,assignment]
    KnowledgeSearchResult = None  # type: ignore[misc,assignment]
    GraphDomain = None  # type: ignore[misc,assignment]
    KnowledgeGraphEngine = None  # type: ignore[misc,assignment]
    get_knowledge_graph = None  # type: ignore[misc,assignment]
    reset_knowledge_graph = None  # type: ignore[misc,assignment]
    CrossAgentKnowledgeBus = None  # type: ignore[misc,assignment]
    get_cross_agent_bus = None  # type: ignore[misc,assignment]
    reset_cross_agent_bus = None  # type: ignore[misc,assignment]

# ── Phase E2: Conversational Memory v2 ────────────────────
try:
    from src.core.conversational.memory_v2 import (
        MemoryTier,
        MemoryType,
        MemoryRecord,
        MemoryQuery,
        MemorySearchResult,
        ContextWindow,
        MemoryEngineV2,
        get_memory_engine_v2,
        reset_memory_engine_v2,
        ContextManager,
        get_context_manager,
        reset_context_manager,
    )
except ImportError as exc:
    logger.warning("core: MemoryV2 import failed: %s", exc)
    MemoryTier = None  # type: ignore[misc,assignment]
    MemoryType = None  # type: ignore[misc,assignment]
    MemoryRecord = None  # type: ignore[misc,assignment]
    MemoryQuery = None  # type: ignore[misc,assignment]
    MemorySearchResult = None  # type: ignore[misc,assignment]
    ContextWindow = None  # type: ignore[misc,assignment]
    MemoryEngineV2 = None  # type: ignore[misc,assignment]
    get_memory_engine_v2 = None  # type: ignore[misc,assignment]
    reset_memory_engine_v2 = None  # type: ignore[misc,assignment]
    ContextManager = None  # type: ignore[misc,assignment]
    get_context_manager = None  # type: ignore[misc,assignment]
    reset_context_manager = None  # type: ignore[misc,assignment]

# ── Phase E3: Self-Learning Loop ──────────────────────────
try:
    from src.core.learning import (
        OutcomeStatus,
        ActionOutcome,
        OutcomeTracker,
        get_outcome_tracker,
        reset_outcome_tracker,
        LearningInsight,
        LearningStrategy,
        LearningEngine,
        get_learning_engine,
        reset_learning_engine,
    )
except ImportError as exc:
    logger.warning("core: Learning import failed: %s", exc)
    OutcomeStatus = None  # type: ignore[misc,assignment]
    ActionOutcome = None  # type: ignore[misc,assignment]
    OutcomeTracker = None  # type: ignore[misc,assignment]
    get_outcome_tracker = None  # type: ignore[misc,assignment]
    reset_outcome_tracker = None  # type: ignore[misc,assignment]
    LearningInsight = None  # type: ignore[misc,assignment]
    LearningStrategy = None  # type: ignore[misc,assignment]
    LearningEngine = None  # type: ignore[misc,assignment]
    get_learning_engine = None  # type: ignore[misc,assignment]
    reset_learning_engine = None  # type: ignore[misc,assignment]

# ── Phase F1: Plugin SDK ──────────────────────────────────
try:
    from src.core.plugins import (
        PluginState,
        PluginCapability,
        PluginManifest,
        PluginInstance,
        PluginRegistry,
        get_plugin_registry,
        reset_plugin_registry,
        PluginLifecycleManager,
        get_plugin_lifecycle,
        reset_plugin_lifecycle,
        HookType,
        HookRegistration,
        PluginHookSystem,
        get_plugin_hook_system,
        reset_plugin_hook_system,
    )
except ImportError as exc:
    logger.warning("core: Plugins import failed: %s", exc)
    PluginState = None  # type: ignore[misc,assignment]
    PluginCapability = None  # type: ignore[misc,assignment]
    PluginManifest = None  # type: ignore[misc,assignment]
    PluginInstance = None  # type: ignore[misc,assignment]
    PluginRegistry = None  # type: ignore[misc,assignment]
    get_plugin_registry = None  # type: ignore[misc,assignment]
    reset_plugin_registry = None  # type: ignore[misc,assignment]
    PluginLifecycleManager = None  # type: ignore[misc,assignment]
    get_plugin_lifecycle = None  # type: ignore[misc,assignment]
    reset_plugin_lifecycle = None  # type: ignore[misc,assignment]
    HookType = None  # type: ignore[misc,assignment]
    HookRegistration = None  # type: ignore[misc,assignment]
    PluginHookSystem = None  # type: ignore[misc,assignment]
    get_plugin_hook_system = None  # type: ignore[misc,assignment]
    reset_plugin_hook_system = None  # type: ignore[misc,assignment]

# ── Phase F2: Policy-as-Code ──────────────────────────────
try:
    from src.core.policy_code import (
        PolicyEffect,
        PolicyOperator,
        PolicyCondition,
        PolicyStatement,
        PolicyDocument,
        PolicyEvaluationResult,
        PolicyCodeEngine,
        get_policy_code_engine,
        reset_policy_code_engine,
        get_builtin_policies,
        install_builtin_policies,
    )
except ImportError as exc:
    logger.warning("core: PolicyCode import failed: %s", exc)
    PolicyEffect = None  # type: ignore[misc,assignment]
    PolicyOperator = None  # type: ignore[misc,assignment]
    PolicyCondition = None  # type: ignore[misc,assignment]
    PolicyStatement = None  # type: ignore[misc,assignment]
    PolicyDocument = None  # type: ignore[misc,assignment]
    PolicyEvaluationResult = None  # type: ignore[misc,assignment]
    PolicyCodeEngine = None  # type: ignore[misc,assignment]
    get_policy_code_engine = None  # type: ignore[misc,assignment]
    reset_policy_code_engine = None  # type: ignore[misc,assignment]
    get_builtin_policies = None  # type: ignore[misc,assignment]
    install_builtin_policies = None  # type: ignore[misc,assignment]

# ── Phase F3: Risk Prediction ─────────────────────────────
try:
    from src.core.risk import (
        RiskLevel,
        BlastRadiusReport,
        RiskPropagationReport,
        CriticalPathReport,
        CompositeRiskReport,
        RiskPredictionEngine,
        get_risk_prediction_engine,
        reset_risk_prediction_engine,
    )
except ImportError as exc:
    logger.warning("core: Risk import failed: %s", exc)
    RiskLevel = None  # type: ignore[misc,assignment]
    BlastRadiusReport = None  # type: ignore[misc,assignment]
    RiskPropagationReport = None  # type: ignore[misc,assignment]
    CriticalPathReport = None  # type: ignore[misc,assignment]
    CompositeRiskReport = None  # type: ignore[misc,assignment]
    RiskPredictionEngine = None  # type: ignore[misc,assignment]
    get_risk_prediction_engine = None  # type: ignore[misc,assignment]
    reset_risk_prediction_engine = None  # type: ignore[misc,assignment]

# ── Phase F4: Chaos Engineering ───────────────────────────
try:
    from src.core.chaos import (
        ChaosExperimentState,
        FaultType,
        FaultInjection,
        ChaosExperiment,
        ChaosExperimentRunner,
        get_chaos_runner,
        reset_chaos_runner,
        SteadyStateVerifier,
        get_steady_state_verifier,
        reset_steady_state_verifier,
    )
except ImportError as exc:
    logger.warning("core: Chaos import failed: %s", exc)
    ChaosExperimentState = None  # type: ignore[misc,assignment]
    FaultType = None  # type: ignore[misc,assignment]
    FaultInjection = None  # type: ignore[misc,assignment]
    ChaosExperiment = None  # type: ignore[misc,assignment]
    ChaosExperimentRunner = None  # type: ignore[misc,assignment]
    get_chaos_runner = None  # type: ignore[misc,assignment]
    reset_chaos_runner = None  # type: ignore[misc,assignment]
    SteadyStateVerifier = None  # type: ignore[misc,assignment]
    get_steady_state_verifier = None  # type: ignore[misc,assignment]
    reset_steady_state_verifier = None  # type: ignore[misc,assignment]

# ── Native Extension ──────────────────────────────────────
try:
    from src.core.native import HAS_NATIVE
except ImportError:
    HAS_NATIVE = False  # type: ignore[misc,assignment]


__all__ = [
    # Phase 6: Approval
    "ApprovalChain", "ApprovalRequest", "ApprovalResult",
    "ApprovalStatus", "ApprovalPriority",
    "WorkflowEngine", "WorkflowDefinition", "WorkflowStep",
    "get_approval_chain", "get_workflow_engine",
    # Phase 6: Defense
    "AntiTamperingLayer", "TamperSeverity",
    "BinaryHardeningLayer", "HardeningLevel",
    "EncryptionManager", "EncryptionLevel",
    "IntegrityVerifier", "IntegrityStatus",
    "ServerSecretsLayer", "SecretType",
    "DefenseManager", "get_defense_manager",
    # Phase 6: License
    "LicenseManager", "LicenseTier", "LicenseStatus",
    "LicenseInfo", "LicenseVerificationResult",
    "KillSwitchStatus", "HardwareBindingStrength",
    "get_license_manager",
    # Phase 6: Degraded Mode
    "DegradedModeManager", "SystemMode",
    "ModeCapabilities", "ModeTransition",
    "get_degraded_mode_manager",
    # Phase 6: Integration
    "initialize_phase6", "get_phase6_status",
    # Phase A: Observability
    "ForensicEngine", "ForensicEntry", "ForensicReport",
    "ChainVerificationResult", "EvidenceBundle",
    "get_forensic_engine",
    "SnapshotAuditEngine", "SnapshotEntry", "SnapshotPair", "SnapshotDiff",
    "get_snapshot_audit_engine",
    "AuditLogger", "AuditEvent", "AuditEventType", "AuditSeverity",
    "get_audit_logger",
    "HealthAggregator", "HealthStatus", "HealthCheckResult",
    "get_health_aggregator",
    "MetricsCollector", "MetricsConfig", "get_metrics_collector",
    "TracingConfig", "init_tracing", "get_tracer", "trace_span",
    # Phase B: Events
    "TriggerMap", "TriggerMapping", "TriggerCondition",
    "EventConditionOperator", "get_trigger_map",
    # WebhookIngestionEngine removed — external API connection deleted
    "EventSchemaRegistry", "EventSchema",
    "EventValidationResult", "ValidationIssue", "IssueType",
    "get_schema_registry",
    "ReplayQueue", "DeadLetterEvent", "DeadLetterStatus",
    "RetryResult", "BatchRetryResult", "get_replay_queue",
    # Phase B: Workflows
    "DynamicChainComposer", "ComposedChain", "ChainStep",
    "ChainStepResult", "ChainExecutionResult", "ChainValidationResult",
    "get_chain_composer",
    "ChainTemplateLibrary", "ChainTemplate", "TemplateStep",
    "TemplateVariable", "TemplateCategory", "get_template_library",
    "InterWorkflowHandoff", "HandoffRule", "HandoffResult",
    "FieldMapping", "get_inter_workflow_handoff",
    "ConditionalBranching", "BranchRule", "BranchCondition",
    "get_conditional_branching",
    # Phase C: Exceptions
    "ExceptionCategory", "ExceptionSeverity", "ZenicException",
    "ExceptionContext",
    "ExceptionEngine", "ExceptionSignal", "ExceptionRecord",
    "get_exception_engine",
    "ExceptionRouter", "RoutingRule", "RoutingAction",
    "get_exception_router",
    "ExceptionAnalytics", "ExceptionPattern", "AnalyticsSnapshot",
    "get_exception_analytics",
    # Phase D: Autopilot
    "Objective", "ObjectiveStatus", "ObjectivePriority", "ObjectiveTarget",
    "get_objective_store",
    "KPITracker", "KPIMeasurement", "KPITrend", "get_kpi_tracker",
    "AutopilotPlanner", "PlannedAction", "PlanStep",
    "get_autopilot_planner",
    "ClosedLoopFeedback", "FeedbackCycle", "FeedbackAction",
    "get_closed_loop_feedback",
    "AutonomyLevel", "AutonomyConfig", "get_autonomy_config",
    "AutopilotEngine", "AutopilotStatus", "get_autopilot_engine",
    # Phase D: ROI
    "CostAccumulator", "CostCategory", "CostEntry", "get_cost_accumulator",
    "ValueTracker", "ValueCategory", "ValueEntry", "get_value_tracker",
    "ImpactScorer", "ImpactScore", "get_impact_scorer",
    "ROIDashboardData", "DashboardWidget", "TrendPoint",
    "get_roi_dashboard_data",
    # Phase E1: Knowledge Graph
    "KnowledgeNode", "KnowledgeEdge", "KnowledgeQuery",
    "KnowledgeSearchResult", "GraphDomain",
    "KnowledgeGraphEngine", "get_knowledge_graph", "reset_knowledge_graph",
    "CrossAgentKnowledgeBus", "get_cross_agent_bus", "reset_cross_agent_bus",
    # Phase E2: Memory v2
    "MemoryTier", "MemoryType", "MemoryRecord", "MemoryQuery",
    "MemorySearchResult", "ContextWindow",
    "MemoryEngineV2", "get_memory_engine_v2", "reset_memory_engine_v2",
    "ContextManager", "get_context_manager", "reset_context_manager",
    # Phase E3: Self-Learning
    "OutcomeStatus", "ActionOutcome", "OutcomeTracker",
    "get_outcome_tracker", "reset_outcome_tracker",
    "LearningInsight", "LearningStrategy", "LearningEngine",
    "get_learning_engine", "reset_learning_engine",
    # Phase F1: Plugin SDK
    "PluginState", "PluginCapability", "PluginManifest", "PluginInstance",
    "PluginRegistry", "get_plugin_registry", "reset_plugin_registry",
    "PluginLifecycleManager", "get_plugin_lifecycle", "reset_plugin_lifecycle",
    "HookType", "HookRegistration", "PluginHookSystem",
    "get_plugin_hook_system", "reset_plugin_hook_system",
    # Phase F2: Policy-as-Code
    "PolicyEffect", "PolicyOperator", "PolicyCondition",
    "PolicyStatement", "PolicyDocument",
    "PolicyEvaluationResult", "PolicyCodeEngine",
    "get_policy_code_engine", "reset_policy_code_engine",
    "get_builtin_policies", "install_builtin_policies",
    # Phase F3: Risk Prediction
    "RiskLevel", "BlastRadiusReport", "RiskPropagationReport",
    "CriticalPathReport", "CompositeRiskReport",
    "RiskPredictionEngine", "get_risk_prediction_engine",
    "reset_risk_prediction_engine",
    # Phase F4: Chaos Engineering
    "ChaosExperimentState", "FaultType", "FaultInjection", "ChaosExperiment",
    "ChaosExperimentRunner", "get_chaos_runner", "reset_chaos_runner",
    "SteadyStateVerifier", "get_steady_state_verifier",
    "reset_steady_state_verifier",
    # Native Extension
    "HAS_NATIVE",
]
