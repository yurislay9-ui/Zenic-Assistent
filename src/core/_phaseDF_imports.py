"""
Phase D-F + Native imports: Autopilot, ROI, Knowledge, Memory,
Learning, Plugins, Policy, Risk, Chaos, Native.

Split from src/core/__init__.py for maintainability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

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
