"""Core package exports — re-exports from sub-packages."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from ._exports_part1 import *  # noqa: F403
from ._exports_part2 import *  # noqa: F403

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
