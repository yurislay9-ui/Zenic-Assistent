"""
BaseOrchestrator — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.orchestrator_base import BaseOrchestrator``
still works exactly as before.
"""

from ._init_mixin import InitMixin
from ._api_mixin import APIMixin
from ._phase7_mixin import Phase7Mixin
from ._phase8_mixin import Phase8Mixin
from ._compat_mixin import CompatMixin
from ._imports import (
    logger, Path, Dict, Any, List, Optional,
    initialize_databases, get_projects_dir, load_settings,
    SemanticParser, MacroRouter, GraphASTEngine, APAPlanner,
    GitHubScrapAgent, ASTSurgeon, ReflexionSandbox,
    MerkleLedger, TheoremCache,
    get_isolation_manager, SandboxWorkspace, shutdown_isolation,
    SubtaskDescriptor, AbortiveProtocol, PartialReasoningManager,
    # CodeGenerator removed — module deleted
    # CodeTransformer removed — module deleted
    AnalysisUtils,
    ThinkingEngine, GenerationPlan,
    # AppGenerator removed — module deleted
    AutomationEngine,
    # SchemaDesigner removed — module deleted
    ExecutorRegistry, get_default_registry, LogicBuilder, AuthService,
    ReasoningEngine, ReasoningMode, ReasoningResult,
    # ChainValidator, ChainExecutor, execute_chain_safe, validate_chain, RecoveryAction removed — module deleted
    AgentRunner, AgentCache,
    SurgicalAgent, ReasoningAgent, BusinessLogicAgent,
    # CodeAgent removed — module deleted
    AutomationAgent, ValidationAgent,
)


class BaseOrchestrator(InitMixin, APIMixin, Phase7Mixin, Phase8Mixin, CompatMixin):
    """
    Shared base for ZenicOrchestrator and DAGOrchestrator.

    Contains all initialization, public API, backward-compat delegation,
    and shared properties that were previously duplicated between the two
    orchestrator implementations.
    """


__all__ = [
    "BaseOrchestrator",
    # Re-export all imports for backward compatibility
    "logger", "Path", "Dict", "Any", "List", "Optional",
    "initialize_databases", "get_projects_dir", "load_settings",
    "SemanticParser", "MacroRouter", "GraphASTEngine", "APAPlanner",
    "GitHubScrapAgent", "ASTSurgeon", "ReflexionSandbox",
    "MerkleLedger", "TheoremCache",
    "get_isolation_manager", "SandboxWorkspace", "shutdown_isolation",
    "SubtaskDescriptor", "AbortiveProtocol", "PartialReasoningManager",
    # "CodeGenerator" removed — module deleted
    # "CodeTransformer" removed — module deleted
    "AnalysisUtils",
    "ThinkingEngine", "GenerationPlan",
    # "AppGenerator" removed — module deleted
    "AutomationEngine",
    # "SchemaDesigner" removed — module deleted
    "ExecutorRegistry", "get_default_registry", "LogicBuilder", "AuthService",
    "ReasoningEngine", "ReasoningMode", "ReasoningResult",
    # "ChainValidator", "ChainExecutor", "execute_chain_safe", "validate_chain", "RecoveryAction" removed — module deleted
    "AgentRunner", "AgentCache",
    "SurgicalAgent", "ReasoningAgent", "BusinessLogicAgent",
    # "CodeAgent" removed — module deleted
    "AutomationAgent", "ValidationAgent",
]
