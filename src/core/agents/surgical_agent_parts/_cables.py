"""
SurgicalAgent 4 cables (classification signals) + signal fusion mixin.
"""

import logging
from typing import Optional, Dict, Any

from ._imports import (
    IntentOutput, VALID_OPERATIONS, VALID_GOALS,
    OP_KW, GOAL_KW, logger,
)


class CablesMixin:
    """4 classification cables and multi-signal fusion for SurgicalAgent."""

    # ============================================================
    #  CALIBRACIÓN ADAPTATIVA (aprende de aciertos/fallos)
    # ============================================================

    def report_accuracy(self, operation: str, was_correct: bool) -> None:
        """Reporta si la clasificación fue correcta (feedback loop)."""
        if operation in self._calibration:
            if was_correct:
                self._calibration[operation]["hits"] += 1
            else:
                self._calibration[operation]["misses"] += 1

    def get_calibration_factor(self, operation: str) -> float:
        """Factor de calibración basado en historial (0.5-1.5)."""
        if operation not in self._calibration:
            return 1.0
        cal = self._calibration[operation]
        total = cal["hits"] + cal["misses"]
        if total < 3:
            return 1.0  # Sin datos suficientes
        accuracy = cal["hits"] / total
        # Factor > 1.0 = aumenta confianza (historial bueno)
        # Factor < 1.0 = reduce confianza (historial malo)
        return 0.5 + accuracy  # Rango: 0.5 - 1.5

    # ============================================================
    #  4 CABLES DE CLASIFICACIÓN (en orden de costo)
    # ============================================================

    def _cable_memory(self, message: str) -> Optional[IntentOutput]:
        """CABLE 1: SmartMemory cache lookup (0ms LLM)."""
        if not self._smart_memory:
            return None
        try:
            cached = self._smart_memory.check_cache(message)
            if cached and cached.get("operation") and cached.get("goal"):
                op = cached["operation"]
                goal = cached["goal"]
                if op in VALID_OPERATIONS and goal in VALID_GOALS:
                    return IntentOutput(
                        operation=op, goal=goal,
                        target=cached.get("target", "unknown"),
                        language=cached.get("language", "python"),
                        entities=cached.get("entities", {}),
                        template_type=cached.get("template_type", "generic"),
                        criticality=cached.get("criticality", "standard"),
                        confidence=min(cached.get("importance", 0.5) * 1.1, 1.0),
                        source="cache",
                    )
        except Exception as e:
            logger.debug(f"SurgicalAgent: Memory cable failed: {e}")
        return None

    def _cable_semantic(self, message: str) -> Optional[IntentOutput]:
        """CABLE 2: SemanticEngine embeddings classification."""
        if not self._semantic_engine or not self._semantic_engine.is_loaded:
            return None
        try:
            sem_result = self._semantic_engine.classify_intent(message)
            if sem_result and sem_result.confidence > 0.3:
                target, lang = self._extract_target_and_lang(message)
                code_lang, _ = self._extract_code_block(message)
                entities = self._extract_entities(message)
                return IntentOutput(
                    operation=sem_result.operation,
                    goal=sem_result.goal,
                    target=target,
                    language=code_lang or lang,
                    entities=entities,
                    template_type=self._infer_template(sem_result.operation, target),
                    criticality=self._infer_criticality(message),
                    confidence=sem_result.confidence,
                    source="semantic",
                )
        except Exception as e:
            logger.debug(f"SurgicalAgent: Semantic cable failed: {e}")
        return None

    def _cable_tfidf(self, message: str) -> IntentOutput:
        """CABLE 4: TF-IDF + regex determinista (siempre funciona)."""
        text_lower = message.lower()

        # Operation scoring (word boundary > substring)
        best_op, best_op_score = "SEARCH", 0
        for op, keywords in OP_KW.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_op_score:
                best_op, best_op_score = op, score

        # Goal scoring
        best_goal, best_goal_score = "FEATURE_ADD", 0
        for goal, keywords in GOAL_KW.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_goal_score:
                best_goal, best_goal_score = goal, score

        # Target + language extraction
        target, lang = self._extract_target_and_lang(message)
        code_lang, _ = self._extract_code_block(message)
        entities = self._extract_entities(message)

        # Confidence: normalizado al rango 0.0-0.5 para fallback
        confidence = min((best_op_score + best_goal_score) / 20.0, 0.5)

        return IntentOutput(
            operation=best_op, goal=best_goal,
            target=target, language=code_lang or lang,
            entities=entities,
            template_type=self._infer_template(best_op, target),
            criticality=self._infer_criticality(message),
            confidence=confidence,
            source="tfidf",
        )

    # ============================================================
    #  FUSIÓN MULTI-SEÑAL (corazón del SurgicalAgent)
    # ============================================================

    def _fuse_signals(self, primary: IntentOutput,
                      secondary: Optional[IntentOutput]) -> IntentOutput:
        """
        Fusiona dos señales de clasificación con calibración adaptativa.

        Reglas de fusión:
        - Si ambas coinciden en operation → confianza ALTA
        - Si discrepan → prima la señal con mayor confianza, pero se reduce
        - Calibración: se aplica factor adaptativo por operation
        """
        if secondary is None:
            # Sin segunda señal, aplicar calibración
            cal_factor = self.get_calibration_factor(primary.operation)
            primary.confidence = min(primary.confidence * cal_factor, 1.0)
            primary.source = primary.source  # Preservar origen
            return primary

        # Ambas señales disponibles
        if primary.operation == secondary.operation and primary.goal == secondary.goal:
            # CONCORDANCIA TOTAL: confianza alta
            confidence = min((primary.confidence + secondary.confidence) / 2 + 0.15, 1.0)
            source = f"{primary.source}+{secondary.source}"
        elif primary.operation == secondary.operation:
            # Concordancia parcial en operation
            confidence = max(primary.confidence, secondary.confidence) * 0.9
            # Usar goal de la señal con mayor confianza
            goal = primary.goal if primary.confidence >= secondary.confidence else secondary.goal
            primary.goal = goal
            source = f"{primary.source}+{secondary.source}"
        else:
            # DISCREPANCIA: prima la de mayor confianza, pero se reduce
            if secondary.confidence > primary.confidence + 0.15:
                # La secundaria es significativamente mejor
                primary.operation = secondary.operation
                primary.goal = secondary.goal
                confidence = secondary.confidence * 0.85
            else:
                confidence = primary.confidence * 0.85
            source = primary.source

        # Aplicar calibración adaptativa
        cal_factor = self.get_calibration_factor(primary.operation)
        primary.confidence = min(confidence * cal_factor, 1.0)
        primary.source = source

        return primary
