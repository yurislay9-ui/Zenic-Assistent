"""
Shared imports and constants for orch_base_parts sub-modules.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config.loader import load_settings
from src.core.shared.db_initializer import initialize_databases, get_projects_dir
from src.core.level1_semantic_engine.parser import SemanticParser
from src.core.level2_macro_router.router import MacroRouter
from src.core.level3_graph_ast.engine import GraphASTEngine
from src.core.level4_apa_planner.planner import APAPlanner

# Level 5 & 6 modules removed in v3.0.0 integrity sweep
try:
    from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent  # type: ignore[import-unresolved]
    from src.core.level5_structural_swarm.ast_surgeon import ASTSurgeon  # type: ignore[import-unresolved]
except ImportError:
    GitHubScrapAgent = None  # type: ignore[misc,assignment]
    ASTSurgeon = None  # type: ignore[misc,assignment]

try:
    from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox  # type: ignore[import-unresolved]
except ImportError:
    ReflexionSandbox = None  # type: ignore[misc,assignment]

from src.core.level7_merkle_ledger.ledger import MerkleLedger
from src.core.level8_theorem_cache.cache import TheoremCache
from src.core.shared.sandbox_isolation import (
    get_isolation_manager, SandboxWorkspace, shutdown_isolation
)

# Decomposed modules
from src.core.subtask_descriptor import SubtaskDescriptor

# AbortiveProtocol — module doesn't exist yet in v3.0.0
try:
    from src.core.abortive_protocol import AbortiveProtocol  # type: ignore[import-unresolved]
except ImportError:
    AbortiveProtocol = None  # type: ignore[misc,assignment]

# PartialReasoningManager — restored import with safe fallback
try:
    from src.core.partial_reasoning import PartialReasoningManager
except ImportError:
    PartialReasoningManager = None  # type: ignore[misc,assignment]

# CodeGenerator and CodeTransformer removed — Zenic is an assistant agent, not a code generator
from src.core.analysis_utils import AnalysisUtils

# Extended AI Architecture
from src.core.thinking_engine import ThinkingEngine, GenerationPlan
from src.core.automation_engine import AutomationEngine

# Phase 7: Real Engines
from src.core.action_executor import ExecutorRegistry, get_default_registry
from src.core.logic_builder import LogicBuilder
from src.core.auth_service import AuthService

# Phase 8: Intelligence
from src.core.reasoning_engine import ReasoningEngine, ReasoningMode, ReasoningResult

# Agent Framework (F1-F5) — migrated to agents with compat adapters
from src.core.agents.compat import (
    AgentRunnerCompat as AgentRunner,
    SurgicalAgentCompat as SurgicalAgent,
    ReasoningAgentCompat as ReasoningAgent,
    BusinessLogicAgentCompat as BusinessLogicAgent,
    AutomationAgentCompat as AutomationAgent,
    ValidationAgentCompat as ValidationAgent,
)
from src.core.agents.infrastructure import AgentCache

logger = logging.getLogger(__name__)
