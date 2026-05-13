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
from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
from src.core.level5_structural_swarm.ast_surgeon import ASTSurgeon
from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox
from src.core.level7_merkle_ledger.ledger import MerkleLedger
from src.core.level8_theorem_cache.cache import TheoremCache
from src.core.shared.sandbox_isolation import (
    get_isolation_manager, SandboxWorkspace, shutdown_isolation
)

# Decomposed modules
from src.core.subtask_descriptor import SubtaskDescriptor
from src.core.abortive_protocol import AbortiveProtocol
from src.core.partial_reasoning import PartialReasoningManager
from src.core.code_generator import CodeGenerator
from src.core.code_transformer import CodeTransformer
from src.core.analysis_utils import AnalysisUtils

# Extended AI Architecture
from src.core.thinking_engine import ThinkingEngine, GenerationPlan
from src.core.app_generator import AppGenerator
from src.core.automation_engine import AutomationEngine
from src.core.schema_designer import SchemaDesigner

# Phase 7: Real Engines
from src.core.action_executor import ExecutorRegistry, get_default_registry
from src.core.logic_builder import LogicBuilder
from src.core.auth_service import AuthService

# Phase 8: Intelligence
from src.core.reasoning_engine import ReasoningEngine, ReasoningMode, ReasoningResult
from src.core.chain_validator import ChainValidator, ChainExecutor, execute_chain_safe, validate_chain, RecoveryAction

# Agent Framework (F1-F5)
from src.core.agents import AgentRunner, AgentCache
from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent

logger = logging.getLogger(__name__)
