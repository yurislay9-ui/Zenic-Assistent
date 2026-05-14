"""Advanced data types for v18 single-responsibility agents.

Layer 4 (Code) + Layer 5 (Validation) + Layer 6 (Automation)
+ Layer 7 (Reasoning) + Layer 8 (Verdict) + Layer 9 (Infrastructure).

E-13 FIX: TriggerSpec, ActionSpec, ScheduleSpec, ValidationIssue are now
defined in shared/agent_schemas.py (single source of truth). This module
re-exports them to maintain backward compatibility for existing imports
from agents_v2.schemas.types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Re-export shared types from single source of truth ──
# E-13 FIX: These types now live in shared/agent_schemas.py to break
# the circular dependency (agents/ → agents_v2/).
from src.core.shared.agent_schemas import (
    ValidationIssue,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
)


# ────────────────────────────── Layer 4: Code ──────────────────────────────

@dataclass
class CodeRequest:
    """Input for code operation agents."""
    task: str = "generate"  # generate|refactor|optimize|fix|scaffold
    requirements: str = ""
    language: str = "python"
    existing_code: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeResult:
    """A17-A22 code agents output."""
    code: str = ""
    language: str = "python"
    files: list[dict[str, str]] = field(default_factory=list)  # [{path, content}]
    changes: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    injected_patterns: list[str] = field(default_factory=list)
    audit_entries: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ScaffoldResult:
    """A21 ProjectScaffolder output."""
    files: list[dict[str, str]] = field(default_factory=list)
    structure: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 5: Validation ──────────────────────────────

# ValidationIssue is now imported from shared/agent_schemas.py (see top of file)


@dataclass
class SecurityResult:
    """A23 SecurityScanner output."""
    safe: bool = True
    threats: list[ValidationIssue] = field(default_factory=list)
    risk_score: float = 0.0
    source: str = "deterministic"


@dataclass
class SyntaxResult:
    """A24 SyntaxValidator output."""
    valid: bool = True
    errors: list[ValidationIssue] = field(default_factory=list)
    line_numbers: list[int] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ChainResult:
    """A25 ChainValidator output."""
    valid: bool = True
    incompatibilities: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ConfigResult:
    """A26 ConfigValidator output."""
    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    defaults_applied: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class RiskResult:
    """A27 RiskCalculator output."""
    score: float = 0.0
    level: str = "low"  # low|medium|high|critical
    recommendations: list[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class FixSuggestions:
    """A28 FixSuggester output."""
    suggestions: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    auto_fixable: list[str] = field(default_factory=list)
    source: str = "deterministic"


# ────────────────────────────── Layer 6: Automation ──────────────────────────────

@dataclass
class AutoDescription:
    """Input for automation agents."""
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)


# TriggerSpec, ActionSpec, ScheduleSpec are now imported from
# shared/agent_schemas.py (see top of file). They are re-exported
# so existing `from agents_v2.schemas.types import TriggerSpec` still works.


@dataclass
class ConditionResult:
    """A32 ConditionExtractor output."""
    conditions: list[str] = field(default_factory=list)
    logic_tree: dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


@dataclass
class NameResult:
    """A33 AutomationNamer output."""
    name: str = ""
    slug: str = ""
    source: str = "deterministic"


@dataclass
class WorkflowSpec:
    """A34 WorkflowSerializer output."""
    yaml: str = ""
    json_spec: str = ""
    executable: dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 7: Reasoning ──────────────────────────────

@dataclass
class ProblemType:
    """A35 ProblemDetector output."""
    type: str = "general"  # api|auth|database|invoice|inventory|crm|automation|general
    subtype: str = ""
    complexity: float = 0.5  # 0.0-1.0
    source: str = "deterministic"


@dataclass
class ReasoningStep:
    """A single reasoning step."""
    step_number: int = 0
    description: str = ""
    conclusion: str = ""
    confidence: float = 0.0


@dataclass
class ReasoningResult:
    """A37 TemplateReasoner output."""
    answer: str = ""
    template_used: str = ""
    confidence: float = 0.0
    steps: list[ReasoningStep] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ConfidenceResult:
    """A38 ConfidenceEstimator output."""
    score: float = 0.0
    factors: list[str] = field(default_factory=list)
    recommendation: str = "proceed"  # proceed|caution|reject
    source: str = "deterministic"


@dataclass
class DecomposedSteps:
    """A36 StepDecomposer output."""
    steps: list[ReasoningStep] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    order: list[int] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class Conclusion:
    """A39 ConclusionExtractor output."""
    text: str = ""
    supported_by: list[str] = field(default_factory=list)
    strength: float = 0.0  # 0.0-1.0
    source: str = "deterministic"


# ────────────────────────────── Layer 8: Verdict ──────────────────────────────

class Verdict(str, Enum):
    """The only things the AI can output."""
    YES = "YES"
    NO = "NO"


class EvidenceType(str, Enum):
    """Types of evidence."""
    AST_VALIDATION = "AST_VALIDATION"
    PATTERN_MATCH = "PATTERN_MATCH"
    SECURITY_CHECK = "SECURITY_CHECK"
    TYPE_SAFETY = "TYPE_SAFETY"
    SYNTAX_VALID = "SYNTAX_VALID"
    SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
    CACHE_HIT = "CACHE_HIT"
    REGEX_MATCH = "REGEX_MATCH"
    KEYWORD_CLASSIFY = "KEYWORD_CLASSIFY"
    STRUCTURAL_MATCH = "STRUCTURAL_MATCH"
    RULE_ENGINE = "RULE_ENGINE"
    SANDBOX_PASS = "SANDBOX_PASS"


@dataclass
class Evidence:
    """A piece of evidence for or against a decision."""
    evidence_type: EvidenceType = EvidenceType.KEYWORD_CLASSIFY
    favors: str = "YES"  # "YES" or "NO"
    weight: float = 0.5
    source: str = ""
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsensusResult:
    """A42 ConsensusResolver output."""
    verdict: Verdict = Verdict.NO
    confidence: float = 0.0
    score: float = 0.0
    evidence_for: list[Evidence] = field(default_factory=list)
    evidence_against: list[Evidence] = field(default_factory=list)
    needs_llm: bool = False
    signals_count: int = 0
    unanimous: bool = False
    source: str = "deterministic"


@dataclass
class VerdictInput:
    """A43 VerdictEngine input."""
    question: str = ""
    evidence_for: list[Evidence] = field(default_factory=list)
    evidence_against: list[Evidence] = field(default_factory=list)
    consensus_score: float = 0.0
    context: str = ""
    max_retries: int = 3


@dataclass
class VerdictOutput:
    """A43 VerdictEngine output."""
    verdict: Verdict = Verdict.NO
    confidence: float = 0.0
    source: str = "deterministic"  # "deterministic", "llm_consensus", "fallback_no_model", "fallback_circuit_open"
    evidence_summary: str = ""
    llm_used: bool = False
    llm_raw_response: str = ""
    retry_count: int = 0
    duration_ms: float = 0.0


@dataclass
class PipelineResult:
    """A40 DeterministicPipeline output."""
    classify: Any = None
    extract: Any = None
    pattern: Any = None
    fill: Any = None
    generate: Any = None
    explain: Any = None
    subtask: Any = None
    source: str = "deterministic"


# ────────────────────────────── Layer 9: Infrastructure ──────────────────────────────

# NOTE: CircuitState is defined in resilience/circuit_breaker.py — single source of truth.
# It is re-exported via schemas/__init__.py for convenience.


@dataclass
class HealthSnapshot:
    """A45 HealthMonitor output."""
    healthy: bool = True
    success_rates: dict[str, float] = field(default_factory=dict)
    latencies: dict[str, float] = field(default_factory=dict)
    circuit_breaker_states: dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0
    source: str = "deterministic"


# NOTE: AuditEntry is defined in resilience/audit_logger.py — single source of truth.
# It is re-exported via schemas/__init__.py for convenience.
