"""
Initialization mixin for BaseOrchestrator.
"""

import threading

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


class InitMixin:
    """Initialization methods for BaseOrchestrator."""

    def _init_pipeline_components(self, settings) -> None:
        """Initialize the 8-level pipeline components."""
        initialize_databases()
        self.settings = settings
        self.p_dir = settings.get("project_dir", ".")

        self.parser = SemanticParser()
        self.router = MacroRouter()
        self.ast_engine = GraphASTEngine()
        self.planner = APAPlanner()
        # Level 5 & 6 modules may not exist — guard against None
        self.scrap = GitHubScrapAgent() if GitHubScrapAgent is not None else None
        self.surgeon = ASTSurgeon() if ASTSurgeon is not None else None
        self.sandbox = ReflexionSandbox() if ReflexionSandbox is not None else None
        self.ledger = MerkleLedger()
        self.cache = TheoremCache()

    def _init_ai_architecture(self, semantic, ai, memory) -> None:
        """Wire the 3-layer AI architecture and connect to parser."""
        self._semantic = semantic
        self._ai = ai
        self._memory = memory

        if self._semantic and self._semantic.is_loaded:
            self.parser.set_semantic_engine(self._semantic)
        if self._memory is not None:
            self.parser.set_smart_memory(self._memory)

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
        self._executor_registry = get_default_registry()
        self._logic_builder = LogicBuilder(template_engine=template_engine)
        self._auth = AuthService()

        logger.info(
            f"Phase 7 Engines: ActionExecutor="
            f"{len(getattr(self._executor_registry, 'list_types', lambda: [])())} types | "
            f"LogicBuilder={len(self._logic_builder.list_blocks())} blocks | "
            f"AuthService=ready"
        )

    def _init_phase8_intelligence(self) -> None:
        """Initialize reasoning, chain_validator, chain_executor."""
        self._reasoning = ReasoningEngine(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        # ChainValidator/ChainExecutor removed — code generation pipeline component
        logger.info(
            "Phase 8 Intelligence: ReasoningEngine=3 modes"
        )

    def _init_extended_with_defaults(self) -> None:
        """Initialize extended architecture using already-set _ai, _semantic, _memory."""
        self._thinking = ThinkingEngine(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        self._template_engine = None
        # TemplateEngine removed — code generation component

        self._init_phase7_engines(template_engine=self._template_engine)
        self._init_phase8_intelligence()

        # AppGenerator removed — not part of assistant agent
        self._app_gen = None
        self._automation = AutomationEngine(
            thinking_engine=self._thinking,
            template_engine=self._template_engine,
            executor_registry=self._executor_registry,
        )
        # SchemaDesigner removed — code generation feature
        self._schema_designer = None

        logger.info(
            f"Extended Architecture: ThinkingEngine=ready | "
            f"AutomationEngine=ready"
        )

    def _init_decomposed_modules(self) -> None:
        """Initialize abortive, partial, code_gen, code_transform, analysis."""
        self._abortive = AbortiveProtocol(self) if AbortiveProtocol is not None else None
        self._partial_reasoning = PartialReasoningManager(self) if PartialReasoningManager is not None else None
        # CodeGenerator and CodeTransformer removed — Zenic is an assistant agent
        self._code_gen = None
        self._code_transform = None
        self._analysis = AnalysisUtils(self)

    def _init_agent_framework(self, context_agent=None, criticality_agent=None,
                               zenic_meta_router=None, fractal_gen=None) -> None:
        """Initialize all F1-F5 agents."""
        self._agent_runner = AgentRunner(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
            enable_cache=True,
        )
        if self._semantic and self._semantic.is_loaded:
            self._agent_runner._cache.set_semantic_engine(self._semantic)

        self._surgical_agent = SurgicalAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        agent_status = "ACTIVE" if self._ai and self._ai.is_loaded else "fallback"
        intent_agent_status = (
            f"ACTIVE (sem={self._semantic.is_loaded})"
            if self._semantic else "fallback"
        )
        logger.info(
            f"Agent Framework: AgentRunner={agent_status} | "
            f"SurgicalAgent(F2)={intent_agent_status} | "
            f"Cache=enabled | "
            f"SemanticCache={'ACTIVE' if self._semantic and self._semantic.is_loaded else 'off'}"
        )

        self._reasoning_agent = ReasoningAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._business_logic_agent = BusinessLogicAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        logger.info("Agent Framework F3: ReasoningAgent=ready | BusinessLogicAgent=ready")

        # CodeAgent removed — code generation agent
        self._code_agent = None
        self._automation_agent = AutomationAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._validation_agent = ValidationAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        logger.info(
            "Agent Framework F4-F5: "
            "AutomationAgent=ready | ValidationAgent=ready"
        )

        self._context_agent = context_agent
        self._criticality_agent = criticality_agent
        self._zenic_meta_router = zenic_meta_router
        self._fractal_gen = fractal_gen

    def _init_common_state(self) -> None:
        """Initialize common state: request_count, locks, pending resumptions, patterns."""
        self._request_count = 0
        self._request_count_lock = threading.Lock()
        self._pending_resumptions = {}
        self._resumptions_lock = threading.Lock()
        self._isolation_manager = get_isolation_manager()
        self._current_client_id = "default"
        self._current_tenant_ctx = None  # Phase 2: TenantContext for multitenancy

        # Design Pattern Infrastructure
        self._event_bus = EventBus()
        self._mediator = Mediator()
        self._db_rwlock = ReadWriteLock()

        # Circuit Breakers for external services
        self._llm_circuit = CircuitBreaker(
            name="llm_engine", failure_threshold=5, recovery_timeout=30.0
        )
        self._http_circuit = CircuitBreaker(
            name="http_requests", failure_threshold=3, recovery_timeout=60.0
        )
        self._db_circuit = CircuitBreaker(
            name="database", failure_threshold=10, recovery_timeout=15.0
        )

        # Default retry config for pipeline operations
        self._pipeline_retry = RetryConfig(
            max_attempts=3, base_delay=1.0, max_delay=30.0,
            exponential_base=2, jitter=True, backoff_strategy="exponential"
        )

        logger.info("Pattern Infrastructure: EventBus + Mediator + CircuitBreakers + Retry initialized")

    def _init_god_level_improvements(self) -> None:
        """Initialize niche auto-scraper, context pointer engine, low-power mode."""
        self._niche_auto_scraper = None
        self._niche_cron = None
        try:
            from src.core.niche_auto_scraper import NicheAutoUpdater, NicheCronScheduler  # type: ignore[import-unresolved]
            if self._template_engine:
                niche_loader = self._template_engine._get_niche_loader()
                if niche_loader:
                    self._niche_auto_scraper = NicheAutoUpdater(
                        niche_loader=niche_loader,
                        scrap_agent=self.scrap,
                    )
                    self._niche_cron = NicheCronScheduler(
                        auto_updater=self._niche_auto_scraper,
                        interval_hours=24,
                    )
                    logger.info("Orchestrator: NicheAutoScraper + Cron initialized")
        except ImportError as e:
            logger.debug(f"Orchestrator: NicheAutoScraper not available: {e}")

        self._context_pointer_engine = None
        try:
            from src.core.context_pointer_engine import SignatureIndex  # type: ignore[import-unresolved]
            self._context_pointer_engine = SignatureIndex(project_root=self.p_dir)
            logger.info("Orchestrator: ContextPointerEngine initialized")
        except ImportError as e:
            logger.debug(f"Orchestrator: ContextPointerEngine not available: {e}")

        self._low_power_mode = None
        try:
            from src.core.low_power_sequential import LowPowerSequentialMode
            self._low_power_mode = LowPowerSequentialMode(governor=None)
            logger.info("Orchestrator: LowPowerSequentialMode initialized")
        except ImportError as e:
            logger.debug(f"Orchestrator: LowPowerSequentialMode not available: {e}")

    def _scan_project(self) -> None:
        """Scan project directory if it exists."""
        if Path(self.p_dir).exists():
            self.ast_engine.scan_project(self.p_dir)
