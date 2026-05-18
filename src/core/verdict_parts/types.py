"""
Tipos y dataclasses para la arquitectura de Veredicto.

Toda decisión pasa por evidencia → consenso → veredicto.
La IA solo interviene en el veredicto, y solo con SÍ o NO.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class Verdict(str, Enum):
    """Veredicto binario que la IA puede emitir. Nada más."""
    YES = "YES"
    NO = "NO"


class EvidenceType(str, Enum):
    """Tipos de evidencia que se pueden recolectar."""
    AST_VALIDATION = "ast_validation"           # El AST parseó correctamente
    PATTERN_MATCH = "pattern_match"             # Coincide con patrón conocido
    SECURITY_CHECK = "security_check"           # Pasó verificación de seguridad
    TYPE_SAFETY = "type_safety"                 # Tipos verificados
    SYNTAX_VALID = "syntax_valid"               # Sintaxis válida
    SEMANTIC_SIMILARITY = "semantic_similarity" # Similitud semántica alta
    CACHE_HIT = "cache_hit"                     # Ya verificado antes (TheoremCache)
    REGEX_MATCH = "regex_match"                 # Coincidencia por regex
    KEYWORD_CLASSIFY = "keyword_classify"       # Clasificación por keywords
    STRUCTURAL_MATCH = "structural_match"       # Estructura coincide
    RULE_ENGINE = "rule_engine"                 # Motor de reglas
    SANDBOX_PASS = "sandbox_pass"               # Pasó sandbox


class VerdictConfidence(str, Enum):
    """Niveles de confianza del consenso."""
    HIGH = "high"           # Consenso claro, no necesita IA
    MEDIUM = "medium"       # Mayoría a favor, IA opcional
    LOW = "low"             # Empate o conflicto, IA requerida
    CERTAIN = "certain"     # Unanimidad absoluta, decisión final


@dataclass
class Evidence:
    """Una pieza de evidencia a favor o en contra de una decisión."""
    evidence_type: EvidenceType
    favors: Verdict              # YES o NO
    weight: float                # 0.0 a 1.0, qué tan importante es
    source: str                  # Qué sistema produjo esta evidencia
    detail: str = ""             # Descripción legible
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"Evidence weight must be 0.0-1.0, got {self.weight}")


@dataclass
class DeterministicResult:
    """Resultado de una tarea ejecutada determinísticamente (sin IA)."""
    task_name: str              # classify, extract, generate, validate, etc.
    success: bool               # Se pudo ejecutar sin IA?
    result: Any                 # El resultado determinístico
    confidence: float = 0.0     # Confianza del resultado (0.0-1.0)
    source: str = "deterministic"
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class VerdictInput:
    """Input para el VerdictEngine. Solo se crea cuando hay conflicto."""
    question: str               # La pregunta binaria que la IA debe responder
    evidence_for: List[Evidence]    # Evidencia a favor de YES
    evidence_against: List[Evidence] # Evidencia a favor de NO
    consensus_score: float      # Score del consenso (-1.0 a 1.0, 0 = empate)
    context: str = ""           # Contexto adicional para el prompt
    max_retries: int = 1        # Máximo reintentos antes de fallback a NO


@dataclass
class VerdictOutput:
    """Output del VerdictEngine. Siempre es SÍ o NO, sin ambigüedad."""
    verdict: Verdict            # Siempre YES o NO
    confidence: float           # 0.0-1.0
    source: str                 # "llm", "consensus", "fallback", "certain"
    evidence_summary: str       # Resumen de la evidencia considerada
    llm_used: bool = False      # Se usó la IA?
    llm_raw_response: str = ""  # Respuesta cruda de la IA (para auditoría)
    retry_count: int = 0        # Cuántas veces se intentó con la IA


@dataclass
class ConsensusResult:
    """Resultado del consenso multi-señal."""
    verdict: Verdict
    confidence: VerdictConfidence
    score: float                # -1.0 (NO total) a 1.0 (YES total)
    evidence_for: List[Evidence]
    evidence_against: List[Evidence]
    needs_llm: bool             # True si necesita arbitraje de IA
    signals_count: int          # Cuántas señales se evaluaron
    unanimous: bool             # Todas las señales coinciden?
