"""Core data types for v18 single-responsibility agents.

Base types + Layer 1 (Understanding) + Layer 2 (Memory & Context)
+ Layer 3 (Business).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ────────────────────────────── Base Types ──────────────────────────────

@dataclass
class AgentResult:
    """Universal result wrapper for all agents.

    Unified type — single source of truth for both legacy (agents/)
    and v2 (agents_v2/) code paths.
    """
    success: bool = False
    data: Any = None
    source: str = "deterministic"  # "deterministic", "cached", "fallback", "llm"
    duration_ms: float = 0.0
    confidence: float = 0.0
    error: str = ""
    cache_hit: bool = False


@dataclass
class AgentMessage:
    """Typed message for inter-agent communication."""
    sender: str
    recipient: str
    message_type: str  # "request", "response", "error", "verdict_needed"
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    timestamp: float = 0.0
    trace_id: str = ""


# ────────────────────────────── Layer 1: Understanding ──────────────────────────────

@dataclass
class LanguageResult:
    """A48 BilingualRouter output."""
    lang: str = "en"
    text: str = ""
    confidence: float = 1.0
    source: str = "deterministic"


@dataclass
class IntentResult:
    """A01 IntentClassifier output."""
    operation: str = "SEARCH"      # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"      # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    confidence: float = 0.0
    source: str = "deterministic"
    evidence: dict[str, float] = field(default_factory=dict)


@dataclass
class EntityResult:
    """A02 EntityExtractor output."""
    files: list[str] = field(default_factory=list)
    langs: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class TargetResult:
    """A03 TargetResolver output."""
    target_file: str = ""
    language: str = "python"
    scope: str = "new_module"  # "new_module", "existing_file", "project"
    source: str = "deterministic"


@dataclass
class CriticalityResult:
    """A04 CriticalityScorer output."""
    level: int = 1                # 1=FAST_STANDARD, 2=DEEP_MODERATE, 3=SURGICAL_CRITICAL
    path: str = "fast_standard"
    reason: str = ""
    confidence: float = 0.0
    adjustments: dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 2: Memory & Context ──────────────────────────────

@dataclass
class MemoryEntries:
    """A05 MemoryCollector output."""
    working: list[dict[str, Any]] = field(default_factory=list)
    long_term: list[dict[str, Any]] = field(default_factory=list)
    episodic: list[dict[str, Any]] = field(default_factory=list)
    procedural: list[dict[str, Any]] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ScoredEntry:
    """A single scored memory entry."""
    content: str = ""
    importance: float = 0.0
    recency: float = 0.0
    relevance: float = 0.0
    combined_score: float = 0.0
    source_type: str = ""  # "working", "long_term", "episodic", "procedural"


@dataclass
class ScoredEntries:
    """A06 RelevanceScorer output."""
    entries: list[ScoredEntry] = field(default_factory=list)
    deduplicated: bool = False
    source: str = "deterministic"


@dataclass
class CompressedContext:
    """A07 ContextCompressor output."""
    text: str = ""
    ratio: float = 1.0
    tokens_used: int = 0
    budget: int = 500
    design_system_preserved: bool = False
    source: str = "deterministic"


@dataclass
class PrefetchResult:
    """A08 ContextPrefetcher output."""
    prefetched: list[dict[str, Any]] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    source: str = "deterministic"


# ────────────────────────────── Layer 3: Business ──────────────────────────────

@dataclass
class BusinessData:
    """Input for business operation agents."""
    type: str = ""   # invoice|inventory|crm|task|report|notification|analytics|custom
    data: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class InvoiceResult:
    """A09 InvoiceProcessor output."""
    totals: dict[str, float] = field(default_factory=dict)
    tax: float = 0.0
    discounts: float = 0.0
    valid: bool = True
    source: str = "deterministic"


@dataclass
class InventoryResult:
    """A10 InventoryManager output."""
    levels: dict[str, int] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)
    reorder: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class CRMResult:
    """A11 CRMPipeline output."""
    stages: list[dict[str, Any]] = field(default_factory=list)
    conversions: dict[str, float] = field(default_factory=dict)
    forecasts: dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


@dataclass
class TaskResult:
    """A12 TaskScheduler output."""
    schedule: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    priorities: dict[str, int] = field(default_factory=dict)
    source: str = "deterministic"


@dataclass
class ReportResult:
    """A13 ReportGenerator output."""
    content: str = ""
    format: str = "text"
    charts: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class NotificationResult:
    """A14 NotificationDispatcher output."""
    sent: bool = False
    channel: str = ""
    status: str = "pending"
    source: str = "deterministic"


@dataclass
class AnalyticsResult:
    """A15 DataAnalyzer output."""
    metrics: dict[str, float] = field(default_factory=dict)
    trends: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class RoutedOperation:
    """A16 OperationRouter output."""
    target_agent: str = ""
    transformed_input: dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 3: Business (Phase D) ──────────────────────────────

@dataclass
class InteractiveCollectionResult:
    """A51 InteractiveDataCollector output.

    Result of an interactive data collection operation for
    completing missing template fields through Q&A dialogue.
    """
    session_id: str = ""
    niche_id: str = ""
    questions: list[dict[str, Any]] = field(default_factory=list)
    answers_applied: int = 0
    answers_rejected: int = 0
    still_missing: int = 0
    completion_pct: float = 0.0
    is_complete: bool = False
    round_number: int = 0
    source: str = "deterministic"


@dataclass
class DomainSafetyResult:
    """Domain-specific safety check result (Phase D).

    Result of the 4-layer extended safety validation including
    domain rules, compliance, and sensitivity escalation.
    """
    base_verdict: str = "ALLOW"
    domain_verdict: str = "ALLOW"
    final_verdict: str = "ALLOW"
    niche_category: str = ""
    data_sensitivity: str = "low"
    domain_rules_matched: list[str] = field(default_factory=list)
    compliance_violations: list[str] = field(default_factory=list)
    escalation_applied: bool = False
    reason: str = ""
    can_proceed: bool = True
    source: str = "deterministic"


@dataclass
class PipelineStepResult:
    """E2E Pipeline step result (Phase D).

    Tracks the result of a single step in the niche onboarding
    pipeline, including state updates and step-specific data.
    """
    step: str = ""
    success: bool = False
    progress_pct: float = 0.0
    pipeline_id: str = ""
    niche_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    source: str = "deterministic"
