"""
Initialization mixin for BaseOrchestrator.

H-83 FIX: Init methods now delegate to OrchestratorPhase classes
for testability, replaceability, and clear boundaries.
The phase classes live in _phases.py and can be tested in isolation.
"""

import logging

from ._imports import (
    logger, Path, initialize_databases, SemanticParser, MacroRouter,
    GraphASTEngine, APAPlanner, GitHubScrapAgent, ASTSurgeon,
    ReflexionSandbox, MerkleLedger, TheoremCache, get_isolation_manager,
    AbortiveProtocol, PartialReasoningManager,
    AnalysisUtils, ThinkingEngine,
    AutomationEngine, get_default_registry, LogicBuilder,
    AuthService, ReasoningEngine,
    AgentRunner, SurgicalAgent, ReasoningAgent,
    BusinessLogicAgent, AutomationAgent, ValidationAgent,
)

from src.core.patterns.orchestration import EventBus, Mediator
from src.core.patterns.resilience import CircuitBreaker, RetryConfig
from src.core.patterns.concurrency import ReadWriteLock
from src.core.orch_base_parts._phases import (
    CommonStatePhase,
    PipelinePhase,
    AIArchitecturePhase,
    ExtendedArchitecturePhase,
    Phase7EnginesPhase,
    Phase8IntelligencePhase,
    DecomposedModulesPhase,
    AgentFrameworkPhase,
    GodLevelImprovementsPhase,
    PHASE_ORDER,
)


class InitMixin:
    """Initialization methods for BaseOrchestrator.

    H-83 FIX: Each _init_* method delegates to an OrchestratorPhase class.
    This enables:
      - Unit testing each phase independently
      - Replacing a phase without modifying the mixin
      - Clear execution boundaries and logging
    """

    def _init_pipeline_components(self, settings) -> None:
        """Initialize the 8-level pipeline components."""
        PipelinePhase.run(self)

    def _init_ai_architecture(self, semantic, ai, memory) -> None:
        """Wire the 3-layer AI architecture and connect to parser."""
        self._semantic = semantic
        self._ai = ai
        self._memory = memory
        AIArchitecturePhase.run(self)

    def _init_extended_architecture(self, thinking_engine=None,
                                     template_engine=None,
                                     executor_registry=None,
                                     logic_builder=None,
                                     auth=None,
                                     reasoning=None,
                                     chain_validator=None,
                                     chain_executor=None,
                                     app_gen=None,
                                     automation=None,
                                     schema_designer=None) -> None:
        """Initialize thinking, template, app, automation, schema engines."""
        self._thinking = thinking_engine
        self._template_engine = template_engine
        self._executor_registry = executor_registry
        self._logic_builder = logic_builder
        self._auth = auth
        self._reasoning = reasoning
        self._chain_validator = chain_validator
        self._chain_executor = chain_executor
        self._app_gen = app_gen
        self._automation = automation
        self._schema_designer = schema_designer

    def _init_phase7_engines(self, template_engine=None) -> None:
        """Initialize executor_registry, logic_builder, auth."""
        self._template_engine = template_engine or self._template_engine
        Phase7EnginesPhase.run(self)

    def _init_phase8_intelligence(self) -> None:
        """Initialize reasoning, chain_validator, chain_executor."""
        Phase8IntelligencePhase.run(self)

    def _init_extended_with_defaults(self) -> None:
        """Initialize extended architecture using already-set _ai, _semantic, _memory."""
        ExtendedArchitecturePhase.run(self)

    def _init_decomposed_modules(self) -> None:
        """Initialize abortive, partial, code_gen, code_transform, analysis."""
        DecomposedModulesPhase.run(self)

    def _init_agent_framework(self, context_agent=None, criticality_agent=None,
                               zenic_meta_router=None, fractal_gen=None) -> None:
        """Initialize all F1-F5 agents."""
        AgentFrameworkPhase.run(self)
        self._context_agent = context_agent
        self._criticality_agent = criticality_agent
        self._zenic_meta_router = zenic_meta_router
        self._fractal_gen = fractal_gen

    def _init_common_state(self) -> None:
        """Initialize common state: request_count, locks, pending resumptions, patterns."""
        CommonStatePhase.run(self)

    def _init_god_level_improvements(self) -> None:
        """Initialize niche auto-scraper, context pointer engine, low-power mode."""
        GodLevelImprovementsPhase.run(self)

    def _scan_project(self) -> None:
        """Scan project directory if it exists."""
        if Path(self.p_dir).exists():
            self.ast_engine.scan_project(self.p_dir)
