"""
ZENIC-AGENTS - Agent Schemas (Pydantic)

Esquemas de entrada/salida para cada agente.
Validación automática de respuestas del LLM.

NOTE: TriggerSpec, ActionSpec, ScheduleSpec, ValidationIssue are now
re-exported from shared/agent_schemas.py (single source of truth).
E-13 FIX: Previously imported from agents_v2/schemas/types which created
a circular dependency (v1 → v2). Now imports from shared/agent_schemas.
"""

from typing import Any, Optional
from dataclasses import dataclass, field

# ── Re-export unified types from shared module (single source of truth) ──
# E-13 FIX: Import from shared/agent_schemas instead of agents_v2 to break
# the circular dependency (agents/ → agents_v2/ was wrong).
from src.core.shared.agent_schemas import (  # noqa: F401
    TriggerSpec, ActionSpec, ScheduleSpec, ValidationIssue,
)


# ============================================================
#  INTENT AGENT SCHEMAS
# ============================================================

@dataclass
class IntentInput:
    """Input para IntentAgent."""
    message: str = ""
    context: str = ""


@dataclass
class IntentOutput:
    """Output de IntentAgent."""
    operation: str = "SEARCH"       # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"       # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    target: str = ""
    language: str = "python"
    entities: dict[str, Any] = field(default_factory=dict)
    template_type: str = "generic"
    criticality: str = "standard"   # standard|moderate|critical
    confidence: float = 0.0
    source: str = "fallback"        # "llm" or "fallback"


# ============================================================
#  REASONING AGENT SCHEMAS
# ============================================================

@dataclass
class ReasoningInput:
    """Input para ReasoningAgent."""
    query: str = ""
    mode: str = "step_by_step"  # step_by_step|self_reflect|with_context
    context: str = ""
    max_steps: int = 5


@dataclass
class ReasoningStep:
    """Un paso de razonamiento."""
    step_number: int = 0
    description: str = ""
    conclusion: str = ""


@dataclass
class ReasoningOutput:
    """Output de ReasoningAgent."""
    answer: str = ""
    confidence: float = 0.0
    mode: str = "step_by_step"
    steps: list[ReasoningStep] = field(default_factory=list)
    refinements: int = 0
    context_used: list[str] = field(default_factory=list)
    memory_hits: int = 0
    source: str = "fallback"
    total_duration_ms: int = 0


# ============================================================
#  BUSINESS LOGIC AGENT SCHEMAS
# ============================================================

@dataclass
class BusinessInput:
    """Input para BusinessLogicAgent."""
    operation_type: str = ""    # invoice|inventory|crm|task|report|notification|analytics|custom
    data: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class BusinessOutput:
    """Output de BusinessLogicAgent."""
    success: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source: str = "fallback"


# ============================================================
#  CODE AGENT SCHEMAS
# ============================================================

@dataclass
class CodeInput:
    """Input para CodeAgent."""
    task: str = "generate"      # generate|transform|scaffold|optimize|fix
    requirements: str = ""
    language: str = "python"
    existing_code: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileSpec:
    """Especificación de un archivo generado."""
    path: str = ""
    content: str = ""
    language: str = ""


@dataclass
class CodeOutput:
    """Output de CodeAgent."""
    code: str = ""
    language: str = "python"
    files: list[FileSpec] = field(default_factory=list)
    test_code: str = ""
    explanation: str = ""
    source: str = "fallback"


# ============================================================
#  AUTOMATION AGENT SCHEMAS
# ============================================================

@dataclass
class AutomationInput:
    """Input para AutomationAgent."""
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)


# NOTE: TriggerSpec, ActionSpec, ScheduleSpec are imported from agents_v2/schemas/types.py


@dataclass
class AutomationOutput:
    """Output de AutomationAgent."""
    name: str = "unnamed_automation"
    triggers: list[TriggerSpec] = field(default_factory=list)
    actions: list[ActionSpec] = field(default_factory=list)
    schedule: ScheduleSpec = field(default_factory=ScheduleSpec)
    conditions: list[str] = field(default_factory=list)
    description: str = ""
    source: str = "fallback"


# ============================================================
#  VALIDATION AGENT SCHEMAS
# ============================================================

@dataclass
class ValidationInput:
    """Input para ValidationAgent."""
    target: str = "code"        # code|chain|config
    content: str = ""
    rules: list[str] = field(default_factory=list)
    language: str = "python"


# NOTE: ValidationIssue is imported from agents_v2/schemas/types.py


@dataclass
class ValidationOutput:
    """Output de ValidationAgent."""
    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    source: str = "fallback"


# ============================================================
#  CONTEXT AGENT SCHEMAS (F3)
# ============================================================

@dataclass
class ContextInput:
    """Input para ContextAgent (F3)."""
    message: str = ""
    intent_output: Optional[Any] = None   # IntentOutput from SurgicalAgent (F2)
    max_tokens: int = 500                 # Total context budget


@dataclass
class ContextEntry:
    """Entrada de contexto con score de relevancia."""
    content: str = ""
    source: str = ""          # "working", "long_term", "episodic", "procedural"
    operation: str = ""
    goal: str = ""
    importance: float = 0.5
    recency: float = 1.0      # 0.0-1.0, 1.0 = most recent
    relevance_score: float = 0.0
    token_estimate: int = 0


@dataclass
class ContextOutput:
    """Output de ContextAgent (F3)."""
    compressed_context: str = ""            # Compressed context to inject
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    token_budget: dict[str, int] = field(default_factory=dict)
    context_scores: dict[str, float] = field(default_factory=dict)
    entries_used: int = 0
    entries_total: int = 0
    compression_ratio: float = 1.0
    source: str = "fallback"
    duration_ms: int = 0


# ============================================================
#  CRITICALITY AGENT SCHEMAS (F4)
# ============================================================

@dataclass
class CriticalityInput:
    """Input para CriticalityAgent (F4)."""
    operation: str = "SEARCH"        # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"        # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    target: str = ""                 # File name, function name, or component
    context: str = ""                # Additional context (user message, etc.)
    code_snippet: str = ""           # Code snippet if available
    existing_level: Optional[int] = None  # Pre-existing criticality from MacroRouter


@dataclass
class CriticalityOutput:
    """Output de CriticalityAgent (F4)."""
    level: int = 2                    # 1=FAST_STANDARD, 2=DEEP_MODERATE, 3=SURGICAL_CRITICAL
    path: str = "standard"            # DAG path: low_crit|standard|high_crit
    reason: str = ""                  # Explanation of why this level
    confidence: float = 0.0           # How confident in this assessment
    source: str = "fallback"          # "llm" or "fallback"
    adjustments: dict[str, Any] = field(default_factory=dict)  # Behavioral adjustments for downstream agents
