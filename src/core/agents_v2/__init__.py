"""
ZENIC-AGENTS v1 — Single-Responsibility Agent Architecture

⚠️  EXPERIMENTAL — This module is NOT used by the default pipeline.
The default pipeline (v16 DAGOrchestrator) uses agents from src/core/agents/.
This v2 agent system is used only by the experimental UnifiedDAGOrchestrator (v18).
Enable with: ZENIC_USE_UNIFIED_DAG=1

Every agent has EXACTLY ONE function. No exceptions.
Qwen AI is ONLY used for binary verdicts (YES/NO) through VerdictEngine.
Everything else is 100% deterministic.

INVARIANTS:
  1. No agent may call the LLM directly. ALL LLM calls go through VerdictEngine.
  2. The LLM can only return "YES" or "NO". Any other response is treated as "NO".
  3. Every agent MUST have a deterministic fallback. The system MUST work 100% without AI.
  4. No two agents may share the same responsibility. Duplication is a design error.
  5. Every agent call is audited. Every decision has an evidence trail.
  6. Security veto is absolute. If SecurityScanner says NO, it is NO. No override possible.
"""

# Schemas & types (single source of truth for all data types)
from .schemas import (
    AgentResult, AgentMessage,
    IntentResult, EntityResult, TargetResult, CriticalityResult, LanguageResult,
    MemoryEntries, ScoredEntry, ScoredEntries, CompressedContext, PrefetchResult,
    BusinessData, InvoiceResult, InventoryResult, CRMResult, TaskResult,
    ReportResult, NotificationResult, AnalyticsResult, RoutedOperation,
    CodeRequest, CodeResult, ScaffoldResult,
    SecurityResult, SyntaxResult, ChainResult, ConfigResult, RiskResult,
    FixSuggestions, ValidationIssue,
    AutoDescription, TriggerSpec, ActionSpec, ScheduleSpec, ConditionResult,
    NameResult, WorkflowSpec,
    ProblemType, ReasoningStep, ReasoningResult, DecomposedSteps,
    ConfidenceResult, Conclusion,
    Verdict, VerdictInput, VerdictOutput, Evidence, EvidenceType,
    ConsensusResult, PipelineResult,
    HealthSnapshot, CircuitState, AuditEntry,
)

# Resilience patterns
from .resilience import (
    BaseAgent, AgentCircuitBreaker, CircuitBreakerManager,
    AgentRetryConfig, with_agent_retry,
    AgentBulkhead, BulkheadManager,
    GlobalHealthMonitor, AgentHealthSnapshot,
    AuditLogger,
)

# Layer 1: Understanding
from .understanding import (
    IntentClassifier, EntityExtractor, TargetResolver, CriticalityScorer, BilingualRouter,
)

# Layer 2: Memory & Context
from .memory import (
    MemoryCollector, RelevanceScorer, ContextCompressor, ContextPrefetcher,
)

# Layer 3: Business
from .business import (
    InvoiceProcessor, InventoryManager, CRMPipeline, TaskScheduler,
    ReportGenerator, NotificationDispatcher, DataAnalyzer, OperationRouter,
)

# Layer 4: Code — REMOVED (code_ops module deleted; code generation is not part of assistant-agent)
# CodeGenerator, CodeRefactorer, CodeOptimizer, CodeFixer,
# ProjectScaffolder, DefensiveInjector no longer available

# Layer 5: Validation & Security
from .validation import (
    SecurityScanner, SyntaxValidator, ChainValidator, ConfigValidator,
    RiskCalculator, FixSuggester,
)

# Layer 6: Automation
from .automation import (
    TriggerInferrer, ActionInferrer, ScheduleParser, ConditionExtractor,
    AutomationNamer, WorkflowSerializer,
)

# Layer 7: Reasoning
from .reasoning import (
    ProblemDetector, StepDecomposer, TemplateReasoner,
    ConfidenceEstimator, ConclusionExtractor,
)

# Layer 8: Verdict
from .verdict import (
    DeterministicPipeline, EvidenceCollectorV18,
    ConsensusResolverV18, VerdictEngineV18,
)

# Layer 9: Infrastructure
from .infrastructure import (
    AgentRunner, HealthMonitorAgent, AuditLoggerAgent,
    CircuitBreakerManagerAgent,
)

__all__ = [
    # Schemas & types
    "AgentResult", "AgentMessage",
    "IntentResult", "EntityResult", "TargetResult", "CriticalityResult", "LanguageResult",
    "MemoryEntries", "ScoredEntry", "ScoredEntries", "CompressedContext", "PrefetchResult",
    "BusinessData", "InvoiceResult", "InventoryResult", "CRMResult", "TaskResult",
    "ReportResult", "NotificationResult", "AnalyticsResult", "RoutedOperation",
    # CodeResult types retained in schemas for backward compatibility
    "CodeRequest", "CodeResult", "ScaffoldResult",
    "SecurityResult", "SyntaxResult", "ChainResult", "ConfigResult", "RiskResult",
    "FixSuggestions", "ValidationIssue",
    "AutoDescription", "TriggerSpec", "ActionSpec", "ScheduleSpec", "ConditionResult",
    "NameResult", "WorkflowSpec",
    "ProblemType", "ReasoningStep", "ReasoningResult", "DecomposedSteps",
    "ConfidenceResult", "Conclusion",
    "Verdict", "VerdictInput", "VerdictOutput", "Evidence", "EvidenceType",
    "ConsensusResult", "PipelineResult",
    "HealthSnapshot", "CircuitState", "AuditEntry",
    # Resilience
    "BaseAgent", "AgentCircuitBreaker", "CircuitBreakerManager",
    "AgentRetryConfig", "with_agent_retry",
    "AgentBulkhead", "BulkheadManager",
    "GlobalHealthMonitor", "AgentHealthSnapshot",
    "AuditLogger",
    # Layer 1: Understanding
    "IntentClassifier", "EntityExtractor", "TargetResolver", "CriticalityScorer", "BilingualRouter",
    # Layer 2: Memory & Context
    "MemoryCollector", "RelevanceScorer", "ContextCompressor", "ContextPrefetcher",
    # Layer 3: Business
    "InvoiceProcessor", "InventoryManager", "CRMPipeline", "TaskScheduler",
    "ReportGenerator", "NotificationDispatcher", "DataAnalyzer", "OperationRouter",
    # Layer 4: Code — REMOVED (code_ops deleted)
    # "CodeGenerator", "CodeRefactorer", "CodeOptimizer", "CodeFixer",
    # "ProjectScaffolder", "DefensiveInjector",
    # Layer 5: Validation & Security
    "SecurityScanner", "SyntaxValidator", "ChainValidator", "ConfigValidator",
    "RiskCalculator", "FixSuggester",
    # Layer 6: Automation
    "TriggerInferrer", "ActionInferrer", "ScheduleParser", "ConditionExtractor",
    "AutomationNamer", "WorkflowSerializer",
    # Layer 7: Reasoning
    "ProblemDetector", "StepDecomposer", "TemplateReasoner",
    "ConfidenceEstimator", "ConclusionExtractor",
    # Layer 8: Verdict
    "DeterministicPipeline", "EvidenceCollectorV18",
    "ConsensusResolverV18", "VerdictEngineV18",
    # Layer 9: Infrastructure
    "AgentRunner", "HealthMonitorAgent", "AuditLoggerAgent",
    "CircuitBreakerManagerAgent",
]
