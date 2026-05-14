"""
V18 Pipeline Orchestrator — Connects all single-responsibility agents.

.. deprecated::
    This module is NOT wired into the main execution path.
    The ``DAGOrchestrator`` and ``UnifiedDAGOrchestrator`` handle request
    processing.  This class is retained for future v18 pipeline activation
    but should not be imported or used in production code paths.

6-Phase Pipeline (FULLY WIRED):
  Phase 1: UNDERSTAND  (A48 → A01 → A02 → A03 → A04)
  Phase 2: CONTEXT     (A05 → A06 → A07 → A08)
  Phase 3: EXECUTE     (A16 → A09-A15/A17-A22 → A22 DefensiveInjector)
  Phase 4: VALIDATE    (A23 → A24 → A27 → A28)
  Phase 5: VERDICT     (A41 → A42 → A43 if needed)
  Phase 6: AUDIT       (A45 → A46 → A47)

All phases are deterministic except Phase 5 when AI arbitration is needed.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .understanding import (
    IntentClassifier,
    EntityExtractor,
    TargetResolver,
    CriticalityScorer,
    BilingualRouter,
)
from .memory import (
    MemoryCollector,
    RelevanceScorer,
    ContextCompressor,
    ContextPrefetcher,
)
from .business import (
    InvoiceProcessor,
    InventoryManager,
    CRMPipeline,
    TaskScheduler,
    ReportGenerator,
    NotificationDispatcher,
    DataAnalyzer,
    OperationRouter,
)
from .code_ops import (
    CodeGenerator,
    CodeRefactorer,
    CodeOptimizer,
    CodeFixer,
    ProjectScaffolder,
    DefensiveInjector,
)
from .validation import (
    SecurityScanner,
    SyntaxValidator,
    RiskCalculator,
    FixSuggester,
)
from .automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    ConditionExtractor,
    AutomationNamer,
    WorkflowSerializer,
)
from .reasoning import (
    ProblemDetector,
    StepDecomposer,
    TemplateReasoner,
    ConfidenceEstimator,
    ConclusionExtractor,
)
from .verdict import (
    VerdictEngineV18,
    EvidenceCollectorV18,
    ConsensusResolverV18,
)
from .schemas import (
    Verdict, VerdictOutput, ConsensusResult, Evidence,
    IntentResult, EntityResult, TargetResult, CriticalityResult,
    LanguageResult, SecurityResult, SyntaxResult, RiskResult,
    WorkflowSpec, ProblemType, ReasoningResult, ConfidenceResult, DecomposedSteps, Conclusion,
    TriggerSpec, ActionSpec, ScheduleSpec, ConditionResult, NameResult,
)
from .resilience import (
    CircuitBreakerManager,
    BulkheadManager,
    GlobalHealthMonitor,
    AuditLogger,
)



from ._core_mixin import PipelineOrchestratorCoreMixin
from ._extra_mixin import PipelineOrchestratorExtraMixin

logger = logging.getLogger("zenic_agents.agents_v2.pipeline_orchestrator")

__all__ = ["PipelineOrchestrator", "NicheOnboardingPipeline"]

# Phase D: Niche Onboarding Pipeline
from .niche_onboarding_pipeline import NicheOnboardingPipeline


class PipelineOrchestrator(PipelineOrchestratorCoreMixin, PipelineOrchestratorExtraMixin):
    """
    V18 Pipeline Orchestrator — Fully Wired.

    Orchestrates the 6-phase pipeline with all single-responsibility agents.
    Every phase is deterministic except Phase 5 (verdict) when AI is needed.

    Architecture:
        Phase 1: UNDERSTAND — Classify intent, extract entities, resolve target, score criticality
        Phase 2: CONTEXT — Collect memory, score relevance, compress, prefetch
        Phase 3: EXECUTE — Route to domain agent, execute, inject defensive patterns
        Phase 4: VALIDATE — Security scan, syntax validate, calculate risk, suggest fixes
        Phase 5: VERDICT — Collect evidence, resolve consensus, AI arbiter if needed
        Phase 6: AUDIT — Health monitor, audit log, circuit breaker management
    """

    def __init__(self, mini_ai=None, smart_memory=None, semantic_engine=None) -> None:
        # ── Shared infrastructure ──
        self._cb_manager = CircuitBreakerManager()
        self._bulkhead_manager = BulkheadManager()
        self._health_monitor = GlobalHealthMonitor()
        self._audit_logger = AuditLogger()
        self._mini_ai = mini_ai
        self._smart_memory = smart_memory
        self._semantic_engine = semantic_engine

        # Common kwargs for all agents
        self._ik = dict(
            circuit_breaker_manager=self._cb_manager,
            bulkhead_manager=self._bulkhead_manager,
            health_monitor=self._health_monitor,
            audit_logger=self._audit_logger,
        )

        # ── Phase 1: Understanding ──
        self._bilingual_router = BilingualRouter(**self._ik)
        self._intent_classifier = IntentClassifier(**self._ik)
        self._entity_extractor = EntityExtractor(**self._ik)
        self._target_resolver = TargetResolver(**self._ik)
        self._criticality_scorer = CriticalityScorer(**self._ik)

        # ── Phase 2: Context ──
        self._memory_collector = MemoryCollector(**self._ik)
        self._relevance_scorer = RelevanceScorer(**self._ik)
        self._context_compressor = ContextCompressor(**self._ik)
        self._context_prefetcher = ContextPrefetcher(**self._ik)
        self._context_prefetcher.wire(smart_memory=smart_memory, semantic_engine=semantic_engine)

        # Wire memory/semantic dependencies
        self._memory_collector.wire(smart_memory, semantic_engine)

        # ── Phase 3: Execute — Business ──
        self._operation_router = OperationRouter(**self._ik)
        self._invoice_processor = InvoiceProcessor(**self._ik)
        self._inventory_manager = InventoryManager(**self._ik)
        self._crm_pipeline = CRMPipeline(**self._ik)
        self._task_scheduler = TaskScheduler(**self._ik)
        self._report_generator = ReportGenerator(**self._ik)
        self._notification_dispatcher = NotificationDispatcher(**self._ik)
        self._data_analyzer = DataAnalyzer(**self._ik)

        # ── Phase 3: Execute — Code ──
        self._code_generator = CodeGenerator(**self._ik)
        self._code_refactorer = CodeRefactorer(**self._ik)
        self._code_optimizer = CodeOptimizer(**self._ik)
        self._code_fixer = CodeFixer(**self._ik)
        self._project_scaffolder = ProjectScaffolder(**self._ik)
        self._defensive_injector = DefensiveInjector(**self._ik)

        # ── Phase 4: Validate ──
        self._security_scanner = SecurityScanner(**self._ik)
        self._syntax_validator = SyntaxValidator(**self._ik)
        self._risk_calculator = RiskCalculator(**self._ik)
        self._fix_suggester = FixSuggester(**self._ik)

        # ── Phase 3: Execute — Automation ──
        self._trigger_inferrer = TriggerInferrer(**self._ik)
        self._action_inferrer = ActionInferrer(**self._ik)
        self._schedule_parser = ScheduleParser(**self._ik)
        self._condition_extractor = ConditionExtractor(**self._ik)
        self._automation_namer = AutomationNamer(**self._ik)
        self._workflow_serializer = WorkflowSerializer(**self._ik)

        # ── Phase 3: Execute — Reasoning ──
        self._problem_detector = ProblemDetector(**self._ik)
        self._step_decomposer = StepDecomposer(**self._ik)
        self._template_reasoner = TemplateReasoner(**self._ik)
        self._confidence_estimator = ConfidenceEstimator(**self._ik)
        self._conclusion_extractor = ConclusionExtractor(**self._ik)

        # ── Phase 5: Verdict ──
        self._evidence_collector = EvidenceCollectorV18(**self._ik)
        self._consensus_resolver = ConsensusResolverV18(**self._ik)
        self._verdict_engine = VerdictEngineV18(mini_ai=mini_ai, **self._ik)

        # ── Business agent registry for routing ──
        self._business_agents = {
            "A09_InvoiceProcessor": self._invoice_processor,
            "A10_InventoryManager": self._inventory_manager,
            "A11_CRMPipeline": self._crm_pipeline,
            "A12_TaskScheduler": self._task_scheduler,
            "A13_ReportGenerator": self._report_generator,
            "A14_NotificationDispatcher": self._notification_dispatcher,
            "A15_DataAnalyzer": self._data_analyzer,
        }

    # ══════════════════════════════════════════════════════════
    #  WIRING METHODS
    # ══════════════════════════════════════════════════════════

