"""All shared data types for v18 single-responsibility agents."""

from ._core_types import (
    # Base types
    AgentResult,
    AgentMessage,
    # Layer 1: Understanding
    LanguageResult,
    IntentResult,
    EntityResult,
    TargetResult,
    CriticalityResult,
    # Layer 2: Memory & Context
    MemoryEntries,
    ScoredEntry,
    ScoredEntries,
    CompressedContext,
    PrefetchResult,
    # Layer 3: Business
    BusinessData,
    InvoiceResult,
    InventoryResult,
    CRMResult,
    TaskResult,
    ReportResult,
    NotificationResult,
    AnalyticsResult,
    RoutedOperation,
)

from ._advanced_types import (
    # Layer 4: Code
    CodeRequest,
    CodeResult,
    ScaffoldResult,
    # Layer 5: Validation
    ValidationIssue,
    SecurityResult,
    SyntaxResult,
    ChainResult,
    ConfigResult,
    RiskResult,
    FixSuggestions,
    # Layer 6: Automation
    AutoDescription,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
    ConditionResult,
    NameResult,
    WorkflowSpec,
    # Layer 7: Reasoning
    ProblemType,
    ReasoningStep,
    ReasoningResult,
    DecomposedSteps,
    ConfidenceResult,
    Conclusion,
    # Layer 8: Verdict
    Verdict,
    VerdictInput,
    VerdictOutput,
    Evidence,
    EvidenceType,
    ConsensusResult,
    PipelineResult,
    # Layer 9: Infrastructure
    HealthSnapshot,
)

__all__ = [
    # Base types
    "AgentResult", "AgentMessage",
    # Layer 1: Understanding
    "LanguageResult", "IntentResult", "EntityResult", "TargetResult", "CriticalityResult",
    # Layer 2: Memory & Context
    "MemoryEntries", "ScoredEntry", "ScoredEntries", "CompressedContext", "PrefetchResult",
    # Layer 3: Business
    "BusinessData", "InvoiceResult", "InventoryResult", "CRMResult", "TaskResult",
    "ReportResult", "NotificationResult", "AnalyticsResult", "RoutedOperation",
    # Layer 4: Code
    "CodeRequest", "CodeResult", "ScaffoldResult",
    # Layer 5: Validation
    "ValidationIssue", "SecurityResult", "SyntaxResult", "ChainResult",
    "ConfigResult", "RiskResult", "FixSuggestions",
    # Layer 6: Automation
    "AutoDescription", "TriggerSpec", "ActionSpec", "ScheduleSpec",
    "ConditionResult", "NameResult", "WorkflowSpec",
    # Layer 7: Reasoning
    "ProblemType", "ReasoningStep", "ReasoningResult", "DecomposedSteps",
    "ConfidenceResult", "Conclusion",
    # Layer 8: Verdict
    "Verdict", "VerdictInput", "VerdictOutput", "Evidence", "EvidenceType",
    "ConsensusResult", "PipelineResult",
    # Layer 9: Infrastructure
    "HealthSnapshot",
]
