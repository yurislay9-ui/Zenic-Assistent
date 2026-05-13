"""Shared schemas and types for v18 agent system."""

from .types import (
    # Base types
    AgentResult,
    AgentMessage,
    # Layer 1: Understanding
    IntentResult,
    EntityResult,
    TargetResult,
    CriticalityResult,
    LanguageResult,
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
    # Layer 4: Code
    CodeRequest,
    CodeResult,
    ScaffoldResult,
    # Layer 5: Validation
    SecurityResult,
    SyntaxResult,
    ChainResult,
    ConfigResult,
    RiskResult,
    FixSuggestions,
    ValidationIssue,
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

# Re-export from resilience (single source of truth)
from ..resilience.circuit_breaker import CircuitState
from ..resilience.audit_logger import AuditEntry

__all__ = [
    # Base types
    "AgentResult", "AgentMessage",
    # Layer 1: Understanding
    "IntentResult", "EntityResult", "TargetResult", "CriticalityResult", "LanguageResult",
    # Layer 2: Memory & Context
    "MemoryEntries", "ScoredEntry", "ScoredEntries", "CompressedContext", "PrefetchResult",
    # Layer 3: Business
    "BusinessData", "InvoiceResult", "InventoryResult", "CRMResult", "TaskResult",
    "ReportResult", "NotificationResult", "AnalyticsResult", "RoutedOperation",
    # Layer 4: Code
    "CodeRequest", "CodeResult", "ScaffoldResult",
    # Layer 5: Validation
    "SecurityResult", "SyntaxResult", "ChainResult", "ConfigResult", "RiskResult",
    "FixSuggestions", "ValidationIssue",
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
    # Re-exported from resilience
    "CircuitState", "AuditEntry",
]
