"""
ConsensusResolver - Sistema de consenso determinístico multi-señal.

Evalúa toda la evidencia recolectada y determina si hay consenso
claro o si se necesita arbitraje de la IA.

Lógica de consenso:
  1. Sumar pesos de evidencia a favor (YES) y en contra (NO)
  2. Calcular score normalizado (-1.0 a 1.0)
  3. Si |score| >= threshold_high → Decisión firme, sin IA
  4. Si |score| >= threshold_medium → Decisión moderada, IA opcional
  5. Si |score| < threshold_medium → Empate, IA REQUERIDA

REGLA DE ORO: En caso de duda, siempre se tiende a NO (rechazar).
Es preferible rechazar algo seguro que aprobar algo peligroso.
"""

import logging
from typing import Dict, Any, List, Optional

from .types import (
    Evidence, EvidenceType, Verdict, VerdictConfidence,
    ConsensusResult, DeterministicResult,
)

logger = logging.getLogger(__name__)

# === Umbrales de consenso ===
CONSENSUS_HIGH_THRESHOLD = 0.6      # |score| >= 0.6 → Confianza alta
CONSENSUS_MEDIUM_THRESHOLD = 0.3    # |score| >= 0.3 → Confianza media
CONSENSUS_CERTAIN_THRESHOLD = 0.85  # |score| >= 0.85 → Unanimidad

# === Pesos por tipo de evidencia ===
EVIDENCE_TYPE_WEIGHTS: Dict[EvidenceType, float] = {
    EvidenceType.SECURITY_CHECK: 1.5,       # Seguridad es lo más importante
    EvidenceType.SYNTAX_VALID: 1.2,         # Sintaxis válida es fuerte
    EvidenceType.SANDBOX_PASS: 1.5,         # Pasó sandbox = muy confiable
    EvidenceType.AST_VALIDATION: 1.2,       # AST válido es fuerte
    EvidenceType.CACHE_HIT: 1.3,            # Cache de teoremas es confiable
    EvidenceType.TYPE_SAFETY: 1.1,          # Seguridad de tipos es importante
    EvidenceType.RULE_ENGINE: 1.0,          # Motor de reglas = base
    EvidenceType.PATTERN_MATCH: 0.8,        # Patrones son moderados
    EvidenceType.STRUCTURAL_MATCH: 0.7,     # Estructural es moderado
    EvidenceType.REGEX_MATCH: 0.6,          # Regex es débil
    EvidenceType.KEYWORD_CLASSIFY: 0.5,     # Keywords son débiles
    EvidenceType.SEMANTIC_SIMILARITY: 0.4,  # Semántica es la más débil (sin IA)
}

# === Veto automático: Ciertos tipos de evidencia pueden vetar YES ===
VETO_TYPES = {
    EvidenceType.SECURITY_CHECK,   # Si el security check dice NO, es NO
    EvidenceType.SANDBOX_PASS,     # Si el sandbox falla, es NO
}

# === Dynamic Memory Chip weight multipliers [T2-11] ===
# Memory chip evidence gets boosted weights based on confidence tier:
# - cache_hit with high confidence → 1.8x (strongest: pre-approved by HITL)
# - cache_hit with medium confidence → 1.5x (approved but less validated)
# - cache_hit with low confidence → 1.3x (new mapping, minimal validation)
MEMORY_CHIP_WEIGHT_MULTIPLIERS: Dict[str, float] = {
    "high": 1.8,    # Pre-approved mapping, high confidence
    "medium": 1.5,  # Approved mapping, medium confidence
    "low": 1.3,     # New mapping, minimal validation
}


class ConsensusResolver:
    """
    Resolver de consenso basado en evidencia ponderada.

    Flujo:
      1. Recibe lista de Evidence
      2. Aplica pesos por tipo de evidencia
      3. Calcula score normalizado
      4. Verifica vetos automáticos
      5. Determina si necesita arbitraje de IA

    REGLA CRÍTICA: Si CUALQUIER evidencia de tipo VETO dice NO,
    el veredicto es NO sin importar el score. Esto garantiza
    que el código peligroso NUNCA se apruebe.
    """

    def resolve(self, evidence: List[Evidence],
                question: str = "") -> ConsensusResult:
        """
        Resuelve el consenso basándose en la evidencia.

        Args:
            evidence: Lista de evidencia a evaluar
            question: La pregunta que se está decidiendo (para logging)

        Returns:
            ConsensusResult con el veredicto y si necesita IA
        """
        if not evidence:
            # Sin evidencia, siempre NO (principio de precaución)
            return ConsensusResult(
                verdict=Verdict.NO,
                confidence=VerdictConfidence.CERTAIN,
                score=0.0,
                evidence_for=[],
                evidence_against=[],
                needs_llm=False,
                signals_count=0,
                unanimous=True,
            )

        # Separar evidencia a favor y en contra
        evidence_for = [e for e in evidence if e.favors == Verdict.YES]
        evidence_against = [e for e in evidence if e.favors == Verdict.NO]

        # === PASO 1: Verificar vetos automáticos ===
        for e in evidence_against:
            if e.evidence_type in VETO_TYPES and e.weight >= 0.7:
                logger.warning(
                    f"ConsensusResolver: VETO automático por {e.evidence_type.value} "
                    f"from {e.source}: {e.detail}"
                )
                return ConsensusResult(
                    verdict=Verdict.NO,
                    confidence=VerdictConfidence.CERTAIN,
                    score=-1.0,
                    evidence_for=evidence_for,
                    evidence_against=evidence_against,
                    needs_llm=False,  # No se necesita IA: es NO rotundo
                    signals_count=len(evidence),
                    unanimous=False,
                )

        # === PASO 2: Calcular score ponderado ===
        score_for = 0.0
        score_against = 0.0

        for e in evidence_for:
            type_weight = EVIDENCE_TYPE_WEIGHTS.get(e.evidence_type, 1.0)
            # Apply dynamic multiplier for memory chip evidence
            if e.source.startswith("memory_chip"):
                confidence_tier = "high" if e.weight >= 0.8 else ("medium" if e.weight >= 0.5 else "low")
                type_weight *= MEMORY_CHIP_WEIGHT_MULTIPLIERS.get(confidence_tier, 1.0)
            score_for += e.weight * type_weight

        for e in evidence_against:
            type_weight = EVIDENCE_TYPE_WEIGHTS.get(e.evidence_type, 1.0)
            # Apply dynamic multiplier for memory chip evidence
            if e.source.startswith("memory_chip"):
                confidence_tier = "high" if e.weight >= 0.8 else ("medium" if e.weight >= 0.5 else "low")
                type_weight *= MEMORY_CHIP_WEIGHT_MULTIPLIERS.get(confidence_tier, 1.0)
            score_against += e.weight * type_weight

        total = score_for + score_against
        if total == 0:
            normalized = 0.0
        else:
            # Normalizado: -1.0 (NO total) a 1.0 (YES total)
            normalized = (score_for - score_against) / total

        # === PASO 3: Determinar veredicto y confianza ===
        abs_score = abs(normalized)

        if abs_score >= CONSENSUS_CERTAIN_THRESHOLD:
            # Unanimidad: no se necesita IA
            verdict = Verdict.YES if normalized > 0 else Verdict.NO
            confidence = VerdictConfidence.CERTAIN
            needs_llm = False

        elif abs_score >= CONSENSUS_HIGH_THRESHOLD:
            # Consenso alto: no se necesita IA
            verdict = Verdict.YES if normalized > 0 else Verdict.NO
            confidence = VerdictConfidence.HIGH
            needs_llm = False

        elif abs_score >= CONSENSUS_MEDIUM_THRESHOLD:
            # Consenso medio: IA opcional (no requerida)
            verdict = Verdict.YES if normalized > 0 else Verdict.NO
            confidence = VerdictConfidence.MEDIUM
            needs_llm = False  # Opcional, no requerido

        else:
            # Empate o casi empate: IA REQUERIDA para arbitraje
            # Principio de precaución: si no hay consenso, default a NO
            verdict = Verdict.NO  # Default conservador
            confidence = VerdictConfidence.LOW
            needs_llm = True     # ← Aquí es donde Qwen interviene

        # Verificar unanimidad
        unanimous = len(evidence_against) == 0 or len(evidence_for) == 0

        result = ConsensusResult(
            verdict=verdict,
            confidence=confidence,
            score=normalized,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            needs_llm=needs_llm,
            signals_count=len(evidence),
            unanimous=unanimous,
        )

        logger.info(
            f"ConsensusResolver: verdict={verdict.value}, score={normalized:.2f}, "
            f"confidence={confidence.value}, needs_llm={needs_llm}, "
            f"signals={len(evidence)}, question={question[:50]}"
        )

        return result

    def resolve_classification(self, text: str,
                               evidence: List[Evidence]) -> DeterministicResult:
        """
        Resuelve la clasificación de intención usando evidencia.

        En vez de pedirle a la IA que clasifique, evaluamos
        la evidencia de cada categoría y tomamos la mejor.

        Returns:
            DeterministicResult con la clasificación y su confianza
        """
        # Agrupar evidencia por operación
        op_scores: Dict[str, float] = {}

        for e in evidence:
            if e.evidence_type == EvidenceType.KEYWORD_CLASSIFY:
                op = e.metadata.get("operation") or e.metadata.get("goal")
                if op:
                    if op not in op_scores:
                        op_scores[op] = 0.0
                    op_scores[op] += e.weight

        if not op_scores:
            return DeterministicResult(
                task_name="classify_intent",
                success=False,
                result={"operation": "SEARCH", "goal": "FEATURE_ADD"},
                confidence=0.1,
                source="fallback",
            )

        # Seleccionar la operación con mayor score
        best_op = max(op_scores, key=op_scores.get)  # type: ignore
        best_score = op_scores[best_op]

        # Segunda mejor para comparar
        sorted_ops = sorted(op_scores.items(), key=lambda x: x[1], reverse=True)
        second_score = sorted_ops[1][1] if len(sorted_ops) > 1 else 0.0

        # Confianza basada en distancia entre 1ro y 2do
        gap = best_score - second_score
        confidence = min(gap / best_score, 1.0) if best_score > 0 else 0.0

        # Determinar goal
        goal_evidence = [e for e in evidence if e.source.startswith("goal_")]
        goal_scores: Dict[str, float] = {}
        for e in goal_evidence:
            goal = e.metadata.get("goal")
            if goal:
                goal_scores[goal] = goal_scores.get(goal, 0.0) + e.weight

        best_goal = max(goal_scores, key=goal_scores.get) if goal_scores else "FEATURE_ADD"  # type: ignore

        return DeterministicResult(
            task_name="classify_intent",
            success=True,
            result={"operation": best_op, "goal": best_goal},
            confidence=confidence,
            source="deterministic",
            evidence=evidence,
        )
