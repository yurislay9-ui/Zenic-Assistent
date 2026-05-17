"""
Motor de intencion multi-capa del Asistente.

Reemplaza el IntentClassifier de keyword matching simple
con un sistema de clasificacion en capas:

  Layer 1: Keyword scoring (rapido, determinista)
  Layer 2: Pattern matching (regex + estructura)
  Layer 3: Context-aware (historial + memoria)
  Layer 4: Confidence calibration (ajuste final)

Cada capa refina el resultado de la anterior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..types.base import Result, Ok
from ..types.intent import AssistantIntent, IntentCategory, ConversationMode
from ..types.session import Session
from ..input.parser import ParsedInput
from ..input.enricher import EnrichedInput


# ─── Score por capa ──────────────────────────────────────────

@dataclass
class IntentScore:
    """Score de una categoria en una capa especifica."""
    category: IntentCategory = IntentCategory.UNKNOWN
    score: float = 0.0
    layer: int = 0              # 1=keyword, 2=pattern, 3=context
    evidence: list[str] = field(default_factory=list)


# ─── Layer 1: Keyword Scoring ────────────────────────────────

_KEYWORD_MAP: dict[IntentCategory, tuple[list[str], float]] = {
    IntentCategory.CHAT: (
        ["hola", "hey", "hi", "hello", "buenos", "buenas",
         "gracias", "thanks", "ok", "bien", "perfecto"],
        2.0,
    ),
    IntentCategory.QUESTION: (
        ["que es", "que significa", "como se", "por que",
         "what is", "how does", "why", "explain", "explica",
         "cual es la diferencia", "difference between",
         "definicion", "definition"],
        2.5,
    ),
    IntentCategory.COMMAND: (
        ["limpiar", "reset", "borrar", "clear",
         "ayuda", "help", "comandos", "estado", "status",
         "salir", "exit", "stop"],
        2.0,
    ),
    IntentCategory.CONFIG: (
        ["configura", "ajusta", "cambia la personalidad",
         "configure", "adjust", "change personality",
         "modo tecnico", "modo casual",
         "cambiar idioma", "cambiar tono"],
        2.5,
    ),
    IntentCategory.FEEDBACK: (
        ["no me gusta", "mal", "incorrecto", "wrong",
         "me gusta", "bien", "correcto", "good",
         "intenta de nuevo", "try again"],
        2.0,
    ),
    IntentCategory.CODE_CREATE: (
        ["crear", "generar", "create", "build", "make",
         "nuevo modulo", "nueva funcion", "escribir"],
        3.0,
    ),
    IntentCategory.CODE_DEBUG: (
        ["debug", "fix", "corregir", "error", "bug",
         "arreglar", "no funciona", "broken"],
        3.0,
    ),
    IntentCategory.CODE_REFACTOR: (
        ["refactor", "limpiar codigo", "reestructurar",
         "mejorar estructura", "simplify"],
        3.0,
    ),
    IntentCategory.CODE_OPTIMIZE: (
        ["optimizar", "optimize", "mejorar rendimiento",
         "speed up", "mas rapido", "efficient"],
        3.0,
    ),
    IntentCategory.CODE_ANALYZE: (
        ["analizar", "analyze", "revisar", "review",
         "auditar", "audit", "chequear", "check"],
        2.5,
    ),
    IntentCategory.CODE_EXPLAIN: (
        ["explica este codigo", "explain code", "que hace",
         "how does this work", "entender", "understand"],
        2.5,
    ),
    IntentCategory.AUTOMATION: (
        ["automatizar", "automate", "workflow", "trigger",
         "cron", "schedule", "programar tarea"],
        3.0,
    ),
    IntentCategory.BUSINESS: (
        ["negocio", "business", "invoice", "factura",
         "reporte", "report", "metrica", "kpi"],
        2.5,
    ),
}


def _layer1_keywords(normalized: str) -> list[IntentScore]:
    """Layer 1: Keyword scoring determinista."""
    scores: list[IntentScore] = []

    for category, (patterns, weight) in _KEYWORD_MAP.items():
        score = 0.0
        evidence: list[str] = []
        for pattern in patterns:
            if pattern in normalized:
                score += weight
                evidence.append(pattern)

        if score > 0:
            scores.append(IntentScore(
                category=category,
                score=score,
                layer=1,
                evidence=evidence,
            ))

    return scores


# ─── Layer 2: Pattern Matching ───────────────────────────────

_QUESTION_PATTERNS = [
    re.compile(r"^(que|como|por\s+que|cual|cuando|donde|quien)\b", re.I),
    re.compile(r"^(what|how|why|which|when|where|who)\b", re.I),
    re.compile(r"\?$"),
]

_CODE_PATTERNS = [
    re.compile(r"\b(crear|generar|escribir)\s+(un\s+)?(modulo|archivo|script|funcion|clase)", re.I),
    re.compile(r"\b(create|generate|write)\s+(a\s+)?(module|file|script|function|class)", re.I),
    re.compile(r"\b(arreglar|corregir|fix)\s+(el\s+)?(error|bug|problema)", re.I),
]

_COMMAND_PATTERNS = [
    re.compile(r"^/(help|reset|clear|status|config)", re.I),
    re.compile(r"^(limpiar|reset|borrar|ayuda|estado)\s*$", re.I),
]


def _layer2_patterns(text: str, parsed: ParsedInput) -> list[IntentScore]:
    """Layer 2: Pattern matching con regex."""
    scores: list[IntentScore] = []

    # Preguntas
    q_score = 0.0
    q_evidence: list[str] = []
    for pat in _QUESTION_PATTERNS:
        if pat.search(text):
            q_score += 3.0
            q_evidence.append(pat.pattern)
    if parsed.is_question:
        q_score += 2.0
        q_evidence.append("parsed:is_question")
    if q_score > 0:
        scores.append(IntentScore(
            category=IntentCategory.QUESTION,
            score=q_score, layer=2, evidence=q_evidence,
        ))

    # Codigo
    if parsed.is_code_request or parsed.has_code:
        c_score = 4.0
        c_evidence = ["parsed:is_code_request"]
        if parsed.has_code:
            c_score += 2.0
            c_evidence.append("parsed:has_code")
        scores.append(IntentScore(
            category=IntentCategory.CODE_CREATE,
            score=c_score, layer=2, evidence=c_evidence,
        ))

    # Comandos
    if parsed.is_command:
        scores.append(IntentScore(
            category=IntentCategory.COMMAND,
            score=5.0, layer=2, evidence=["parsed:is_command"],
        ))

    return scores


# ─── Layer 3: Context-Aware ──────────────────────────────────

def _layer3_context(
    enriched: EnrichedInput,
    base_scores: dict[IntentCategory, float],
) -> list[IntentScore]:
    """Layer 3: Ajusta scores basado en contexto conversacional."""
    adjustments: list[IntentScore] = []

    # Si es continuacion de conversacion sobre codigo
    if enriched.is_continuation:
        recent = " ".join(enriched.recent_topics)
        code_words = [
            "codigo", "code", "funcion", "function",
            "clase", "class", "modulo", "module",
        ]
        if any(w in recent for w in code_words):
            for cat in (
                IntentCategory.CODE_CREATE,
                IntentCategory.CODE_DEBUG,
                IntentCategory.CODE_REFACTOR,
            ):
                if cat in base_scores:
                    adjustments.append(IntentScore(
                        category=cat,
                        score=2.0,
                        layer=3,
                        evidence=["continuation:code_context"],
                    ))

    # Si hay memoria relevante sobre codigo
    for entry in enriched.memory_context[:3]:
        source = entry.get("source", "")
        cat_str = entry.get("category", "")
        if source == "code" or cat_str in ("skill", "fact"):
            adjustments.append(IntentScore(
                category=IntentCategory.CODE_CREATE,
                score=1.0,
                layer=3,
                evidence=["memory:code_relevant"],
            ))
            break

    return adjustments


# ─── Intent Engine ────────────────────────────────────────────

class IntentEngine:
    """
    Motor de intencion multi-capa.

    Combina 3 capas de clasificacion para producir
    una intencion con confianza calibrada.
    """

    def classify(
        self,
        enriched: EnrichedInput,
        session: Session | None = None,
    ) -> Result[AssistantIntent, Exception]:
        """
        Clasifica la intencion del mensaje enriquecido.

        Pipeline: L1 keywords → L2 patterns → L3 context → calibrate.
        """
        normalized = enriched.normalized
        text = enriched.text

        # Layer 1: Keywords
        l1_scores = _layer1_keywords(normalized)

        # Layer 2: Patterns
        l2_scores = _layer2_patterns(text, enriched.parsed)

        # Merge scores por categoria
        merged: dict[IntentCategory, float] = {}
        evidence_map: dict[IntentCategory, list[str]] = {}

        for s in l1_scores + l2_scores:
            merged[s.category] = merged.get(s.category, 0.0) + s.score
            if s.category not in evidence_map:
                evidence_map[s.category] = []
            evidence_map[s.category].extend(s.evidence)

        # Layer 3: Context adjustments
        l3_scores = _layer3_context(enriched, merged)
        for s in l3_scores:
            merged[s.category] = merged.get(s.category, 0.0) + s.score
            if s.category not in evidence_map:
                evidence_map[s.category] = []
            evidence_map[s.category].extend(s.evidence)

        # Determinar mejor categoria
        if not merged:
            category = IntentCategory.CHAT
            confidence = 0.3
        else:
            category = max(merged, key=merged.get)  # type: ignore
            max_score = merged[category]
            confidence = min(max_score / 10.0, 1.0)

        # Inferir modo
        mode = self._infer_mode(category, normalized)

        # Construir resultado
        intent = AssistantIntent(
            category=category,
            confidence=confidence,
            mode=mode,
            raw_text=text,
            language=enriched.sanitized.detected_language,
            source="multi_layer",
            entities={
                "evidence": evidence_map.get(category, []),
                "all_scores": {c.value: round(s, 2) for c, s in merged.items()},
                "conversation_turn": enriched.conversation_turn,
            },
        )

        return Ok(intent)

    @staticmethod
    def _infer_mode(category: IntentCategory, text: str) -> ConversationMode:
        """Infiere el modo de conversacion."""
        if category in (
            IntentCategory.CODE_CREATE,
            IntentCategory.CODE_DEBUG,
            IntentCategory.CODE_REFACTOR,
            IntentCategory.CODE_OPTIMIZE,
            IntentCategory.CODE_ANALYZE,
        ):
            return ConversationMode.CODING

        if category == IntentCategory.QUESTION:
            step_words = ["paso a paso", "step by step", "explica", "explain"]
            if any(w in text for w in step_words):
                return ConversationMode.TEACHING
            return ConversationMode.REASONING

        if category == IntentCategory.AUTOMATION:
            return ConversationMode.AUTOMATION

        if category == IntentCategory.CODE_EXPLAIN:
            return ConversationMode.TEACHING

        return ConversationMode.NORMAL
