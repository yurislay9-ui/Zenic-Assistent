"""
Mixin: Fallback and TF-IDF classification methods.
"""

import time as _time
from typing import Any

from ._imports import (
    IntentInput, IntentOutput, VALID_OPERATIONS, VALID_GOALS,
    OP_KEYWORDS, GOAL_KEYWORDS, logger,
)


class FallbackMixin:
    """Fallback, TF-IDF, and SmartMemory caching for IntentAgent."""

    def fallback(self, input_data: Any) -> IntentOutput:
        """
        Fallback determinista: TF-IDF simplificado + regex.

        Sin LLM, sin embeddings, 100% determinista.
        Prioriza: SmartMemory cache → SemanticEngine → TF-IDF + regex
        """
        start = _time.time()

        if isinstance(input_data, IntentInput):
            message = input_data.message
        elif isinstance(input_data, str):
            message = input_data
        else:
            message = str(input_data)

        # 1. SmartMemory cache lookup
        if self._smart_memory:
            try:
                cached = self._smart_memory.check_cache(message)
                if cached and cached.get("operation") and cached.get("goal"):
                    op = cached["operation"]
                    goal = cached["goal"]
                    if op in VALID_OPERATIONS and goal in VALID_GOALS:
                        result = IntentOutput(
                            operation=op,
                            goal=goal,
                            target=cached.get("target", "unknown"),
                            language=cached.get("language", "python"),
                            entities=cached.get("entities", {}),
                            template_type=cached.get("template_type", "generic"),
                            criticality=cached.get("criticality", "standard"),
                            confidence=cached.get("importance", 0.5),
                            source="fallback",
                        )
                        self._update_stats("fallback", int((_time.time() - start) * 1000))
                        return result
            except Exception as e:
                logger.debug(f"IntentAgent: SmartMemory lookup failed: {e}")

        # 2. SemanticEngine classification (if available)
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                sem_result = self._semantic_engine.classify_intent(message)
                if sem_result and sem_result.confidence > 0.3:
                    target, lang = self._extract_target_and_language(message)
                    code_lang, raw_code = self._extract_code_block(message)
                    entities = self._extract_entities(message)

                    output = IntentOutput(
                        operation=sem_result.operation,
                        goal=sem_result.goal,
                        target=target,
                        language=code_lang or lang,
                        entities=entities,
                        template_type=self._infer_template_type(sem_result.operation, target),
                        criticality=self._infer_criticality(message),
                        confidence=sem_result.confidence,
                        source="fallback",
                    )

                    # Cache in SmartMemory
                    self._cache_in_smart_memory(message, output)

                    self._update_stats("fallback", int((_time.time() - start) * 1000))
                    return output
            except Exception as e:
                logger.debug(f"IntentAgent: SemanticEngine classification failed: {e}")

        # 3. Pure TF-IDF + regex fallback (no external deps)
        result = self._tfidf_fallback(message)
        self._update_stats("fallback", int((_time.time() - start) * 1000))
        return result

    def _tfidf_fallback(self, message: str) -> IntentOutput:
        """
        Fallback TF-IDF simplificado + regex.
        Reemplaza la lógica del SemanticParser para clasificación sin modelo.
        """
        text_lower = message.lower()

        # --- Operation classification (keyword scoring) ---
        best_op = "SEARCH"
        best_op_score = 0
        for op, keywords in OP_KEYWORDS.items():
            score = 0
            for kw in keywords:
                # Word boundary match scores higher than substring
                if kw in text_lower.split():
                    score += 2
                elif kw in text_lower:
                    score += 1
            if score > best_op_score:
                best_op_score = score
                best_op = op

        # --- Goal classification (keyword scoring) ---
        best_goal = "FEATURE_ADD"
        best_goal_score = 0
        for goal, keywords in GOAL_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in text_lower.split():
                    score += 2
                elif kw in text_lower:
                    score += 1
            if score > best_goal_score:
                best_goal_score = score
                best_goal = goal

        # --- Target extraction (regex) ---
        target, lang = self._extract_target_and_language(message)
        code_lang, raw_code = self._extract_code_block(message)
        final_lang = code_lang or lang

        # --- Entities extraction ---
        entities = self._extract_entities(message)

        # --- Criticality ---
        criticality = self._infer_criticality(message)

        # --- Template type ---
        template_type = self._infer_template_type(best_op, target)

        # --- Confidence (0-0.5 range for fallback) ---
        confidence = min((best_op_score + best_goal_score) / 20.0, 0.5)

        output = IntentOutput(
            operation=best_op,
            goal=best_goal,
            target=target,
            language=final_lang,
            entities=entities,
            template_type=template_type,
            criticality=criticality,
            confidence=confidence,
            source="fallback",
        )

        # Cache in SmartMemory
        self._cache_in_smart_memory(message, output)

        return output

    def _cache_in_smart_memory(self, message: str, output: IntentOutput) -> None:
        """Cache el resultado en SmartMemory si está disponible."""
        if not self._smart_memory:
            return
        try:
            self._smart_memory.save_to_cache(
                query=message,
                response=f"op={output.operation},goal={output.goal}",
                operation=output.operation,
                goal=output.goal,
                importance=output.confidence,
            )
        except Exception as e:
            logger.debug(f"IntentAgent: Failed to cache in SmartMemory: {e}")
