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
