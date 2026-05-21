"""
OrchestratorPhase — H-83 FIX: Extract init phases from God Object InitMixin.

Each phase encapsulates one logical initialization step. The InitMixin
delegates to these phases, making the initialization pipeline:
  - Testable in isolation
  - Replaceable without touching the mixin
  - Documented with clear boundaries

Usage:
    class InitMixin:
        def _init_common_state(self):
            CommonStatePhase.run(self)
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.core.orch_base_parts._imports import (
        Path, initialize_databases, SemanticParser, MacroRouter,
        GraphASTEngine, APAPlanner, GitHubScrapAgent, ASTSurgeon,
        ReflexionSandbox, MerkleLedger, TheoremCache,
        get_isolation_manager, AbortiveProtocol, PartialReasoningManager,
        AnalysisUtils, ThinkingEngine, AutomationEngine,
        get_default_registry, LogicBuilder, AuthService, ReasoningEngine,
        AgentRunner, SurgicalAgent, ReasoningAgent,
        BusinessLogicAgent, AutomationAgent, ValidationAgent,
    )

logger = logging.getLogger(__name__)


class OrchestratorPhase:
    """Base class for orchestrator initialization phases."""

    name: str = "base"

    @classmethod
    def run(cls, orchestrator: Any) -> None:
        """Execute this phase on the given orchestrator instance."""
        raise NotImplementedError


class CommonStatePhase(OrchestratorPhase):
    """Phase 1: Initialize common state — request counts, locks, patterns."""

    name = "common_state"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.patterns.orchestration import EventBus, Mediator
        from src.core.patterns.resilience import CircuitBreaker, RetryConfig
        from src.core.patterns.concurrency import ReadWriteLock
        from src.core.orch_base_parts._imports import get_isolation_manager

        orch._request_count = 0
        orch._request_count_lock = threading.Lock()
        orch._pending_resumptions: Dict[str, Any] = {}
        orch._resumptions_lock = threading.Lock()
        orch._isolation_manager = get_isolation_manager()
        orch._current_client_id = "default"
        orch._current_tenant_ctx = None  # Phase 2: TenantContext

        # Design Pattern Infrastructure
        orch._event_bus = EventBus()
        orch._mediator = Mediator()
        orch._db_rwlock = ReadWriteLock()

        # Circuit Breakers for external services
        orch._llm_circuit = CircuitBreaker(
            name="llm_engine", failure_threshold=5, recovery_timeout=30.0
        )
        orch._http_circuit = CircuitBreaker(
            name="http_requests", failure_threshold=3, recovery_timeout=60.0
        )
        orch._db_circuit = CircuitBreaker(
            name="database", failure_threshold=10, recovery_timeout=15.0
        )

        # Default retry config
        orch._pipeline_retry = RetryConfig(
            max_attempts=3, base_delay=1.0, max_delay=30.0,
            exponential_base=2, jitter=True, backoff_strategy="exponential"
        )

        logger.info("Phase [common_state]: EventBus + Mediator + CircuitBreakers + Retry initialized")


class PipelinePhase(OrchestratorPhase):
    """Phase 2: Initialize the 8-level pipeline components."""

    name = "pipeline"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.orch_base_parts._imports import (
            initialize_databases, SemanticParser, MacroRouter,
            GraphASTEngine, APAPlanner, GitHubScrapAgent, ASTSurgeon,
            ReflexionSandbox, MerkleLedger, TheoremCache,
        )

        initialize_databases()

        orch.parser = SemanticParser()
        orch.router = MacroRouter()
        orch.ast_engine = GraphASTEngine()
        orch.planner = APAPlanner()
        # Level 5 & 6 — guard against None
        orch.scrap = GitHubScrapAgent() if GitHubScrapAgent is not None else None
        orch.surgeon = ASTSurgeon() if ASTSurgeon is not None else None
        orch.sandbox = ReflexionSandbox() if ReflexionSandbox is not None else None
        orch.ledger = MerkleLedger()
        orch.cache = TheoremCache()

        logger.info("Phase [pipeline]: 8-level pipeline components initialized")


class AIArchitecturePhase(OrchestratorPhase):
    """Phase 3: Wire the 3-layer AI architecture and connect to parser."""

    name = "ai_architecture"

    @classmethod
    def run(cls, orch: Any) -> None:
        if orch._semantic and orch._semantic.is_loaded:
            orch.parser.set_semantic_engine(orch._semantic)
        if orch._memory is not None:
            orch.parser.set_smart_memory(orch._memory)

        logger.info("Phase [ai_architecture]: 3-layer AI wired to parser")


class ExtendedArchitecturePhase(OrchestratorPhase):
    """Phase 4: Initialize thinking, template, app, automation, schema engines."""

    name = "extended_architecture"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.orch_base_parts._imports import (
            ThinkingEngine, AutomationEngine,
        )

        orch._thinking = ThinkingEngine(
            mini_ai=orch._ai,
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )

        orch._template_engine = None  # TemplateEngine removed

        # Sub-phases
        Phase7EnginesPhase.run(orch)
        Phase8IntelligencePhase.run(orch)

        orch._app_gen = None  # AppGenerator removed
        orch._automation = AutomationEngine(
            thinking_engine=orch._thinking,
            template_engine=orch._template_engine,
            executor_registry=orch._executor_registry,
        )
        orch._schema_designer = None  # SchemaDesigner removed

        logger.info("Phase [extended_architecture]: ThinkingEngine + AutomationEngine ready")


class Phase7EnginesPhase(OrchestratorPhase):
    """Phase 4a: Initialize executor_registry, logic_builder, auth."""

    name = "phase7_engines"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.orch_base_parts._imports import (
            get_default_registry, LogicBuilder, AuthService,
        )

        orch._executor_registry = get_default_registry()
        orch._logic_builder = LogicBuilder(template_engine=orch._template_engine)
        orch._auth = AuthService()

        logger.info(
            "Phase [phase7_engines]: ActionExecutor=%d types | LogicBuilder=%d blocks | AuthService=ready",
            len(getattr(orch._executor_registry, 'list_types', lambda: [])()),
            len(orch._logic_builder.list_blocks()),
        )


class Phase8IntelligencePhase(OrchestratorPhase):
    """Phase 4b: Initialize reasoning, chain_validator, chain_executor."""

    name = "phase8_intelligence"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.orch_base_parts._imports import ReasoningEngine

        orch._reasoning = ReasoningEngine(
            mini_ai=orch._ai,
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )
        logger.info("Phase [phase8_intelligence]: ReasoningEngine=3 modes")


class DecomposedModulesPhase(OrchestratorPhase):
    """Phase 5: Initialize abortive, partial, analysis."""

    name = "decomposed_modules"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.orch_base_parts._imports import (
            AbortiveProtocol, PartialReasoningManager, AnalysisUtils,
        )

        orch._abortive = AbortiveProtocol(orch) if AbortiveProtocol is not None else None
        orch._partial_reasoning = PartialReasoningManager(orch) if PartialReasoningManager is not None else None
        orch._code_gen = None  # CodeGenerator removed
        orch._code_transform = None  # CodeTransformer removed
        orch._analysis = AnalysisUtils(orch)

        logger.info("Phase [decomposed_modules]: AbortiveProtocol + AnalysisUtils ready")


class AgentFrameworkPhase(OrchestratorPhase):
    """Phase 6: Initialize all F1-F5 agents."""

    name = "agent_framework"

    @classmethod
    def run(cls, orch: Any) -> None:
        from src.core.orch_base_parts._imports import (
            AgentRunner, SurgicalAgent, ReasoningAgent,
            BusinessLogicAgent, AutomationAgent, ValidationAgent,
        )

        orch._agent_runner = AgentRunner(
            mini_ai=orch._ai,
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
            enable_cache=True,
        )
        if orch._semantic and orch._semantic.is_loaded:
            orch._agent_runner._cache.set_semantic_engine(orch._semantic)

        orch._surgical_agent = SurgicalAgent(
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )

        orch._reasoning_agent = ReasoningAgent(
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )
        orch._business_logic_agent = BusinessLogicAgent(
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )

        orch._code_agent = None  # CodeAgent removed
        orch._automation_agent = AutomationAgent(
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )
        orch._validation_agent = ValidationAgent(
            semantic_engine=orch._semantic,
            smart_memory=orch._memory,
        )

        logger.info("Phase [agent_framework]: F1-F5 agents initialized")


class GodLevelImprovementsPhase(OrchestratorPhase):
    """Phase 7: Initialize niche auto-scraper, context pointer, low-power mode."""

    name = "god_level_improvements"

    @classmethod
    def run(cls, orch: Any) -> None:
        orch._niche_auto_scraper = None
        orch._niche_cron = None
        try:
            from src.core.niche_auto_scraper import NicheAutoUpdater, NicheCronScheduler  # type: ignore[import-unresolved]
            if orch._template_engine:
                niche_loader = orch._template_engine._get_niche_loader()
                if niche_loader:
                    orch._niche_auto_scraper = NicheAutoUpdater(
                        niche_loader=niche_loader, scrap_agent=orch.scrap,
                    )
                    orch._niche_cron = NicheCronScheduler(
                        auto_updater=orch._niche_auto_scraper, interval_hours=24,
                    )
                    logger.info("Phase [god_level]: NicheAutoScraper + Cron initialized")
        except ImportError as e:
            logger.debug("Phase [god_level]: NicheAutoScraper not available: %s", e)

        orch._context_pointer_engine = None
        try:
            from src.core.context_pointer_engine import SignatureIndex  # type: ignore[import-unresolved]
            orch._context_pointer_engine = SignatureIndex(project_root=orch.p_dir)
            logger.info("Phase [god_level]: ContextPointerEngine initialized")
        except ImportError as e:
            logger.debug("Phase [god_level]: ContextPointerEngine not available: %s", e)

        orch._low_power_mode = None
        try:
            from src.core.low_power_sequential import LowPowerSequentialMode
            orch._low_power_mode = LowPowerSequentialMode(governor=None)
            logger.info("Phase [god_level]: LowPowerSequentialMode initialized")
        except ImportError as e:
            logger.debug("Phase [god_level]: LowPowerSequentialMode not available: %s", e)


# ── Phase execution order ──────────────────────────────────
PHASE_ORDER: List[type] = [
    CommonStatePhase,        # 1
    PipelinePhase,           # 2
    AIArchitecturePhase,     # 3
    ExtendedArchitecturePhase,  # 4 (includes 4a + 4b)
    DecomposedModulesPhase,  # 5
    AgentFrameworkPhase,     # 6
    GodLevelImprovementsPhase,  # 7
]
