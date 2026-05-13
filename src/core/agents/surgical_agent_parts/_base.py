"""
SurgicalAgent BaseAgent interface + high-level API mixin.
"""

import time
import logging
from typing import Any, Optional, Tuple

from ._imports import (
    BaseAgent, AgentResult, AgentPrompts,
    IntentInput, IntentOutput,
    VALID_OPERATIONS, VALID_GOALS,
    logger,
)


class BaseInterfaceMixin:
    """BaseAgent interface methods and high-level API for SurgicalAgent."""

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye prompt quirúrgico para clasificación de intención."""
        if isinstance(input_data, IntentInput):
            message = input_data.message
            context = input_data.context
        elif isinstance(input_data, str):
            message = input_data
            context = ""
        else:
            message = str(input_data)
            context = ""

        # Prompt ultra-compacto para Qwen3-0.6B (≤600 tokens)
        system = (
            "Classify intent. Reply ONLY JSON:\n"
            '{"operation":"CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE",'
            '"goal":"COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY",'
            '"target":"file_or_component","language":"python|kotlin|go|js|ts|java|rust|c|cpp|ruby",'
            '"entities":{"key":"value"},"template_type":"api|web|cli|data|mobile|automation|generic",'
            '"criticality":"standard|moderate|critical","confidence":0.0-1.0}'
        )
        user = f"Classify: {message[:400]}"
        if context:
            user += f"\nCtx: {context[:150]}"
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[Any]:
        """Parsea respuesta del LLM a IntentOutput válido."""
        cleaned = self.clean_llm_text(raw_response)
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._dict_to_output(json_data, source="llm")
        return self._parse_freetext(cleaned, source="llm")

    def fallback(self, input_data: Any) -> Optional[IntentOutput]:
        """Fallback determinista: SmartMemory → SemanticEngine → TF-IDF."""
        start = time.time()

        if isinstance(input_data, IntentInput):
            message = input_data.message
        elif isinstance(input_data, str):
            message = input_data
        else:
            message = str(input_data)

        # CABLE 1: SmartMemory cache
        mem_result = self._cable_memory(message)
        if mem_result:
            self._update_stats("fallback", int((time.time() - start) * 1000))
            return mem_result

        # CABLE 2: SemanticEngine embeddings
        sem_result = self._cable_semantic(message)

        # CABLE 4: TF-IDF determinista (siempre disponible)
        tfidf_result = self._cable_tfidf(message)

        # FUSIÓN multi-señal
        fused = self._fuse_signals(tfidf_result, sem_result)

        # Cache en SmartMemory
        self._cache_result(message, fused)

        self._update_stats("fallback", int((time.time() - start) * 1000))
        return fused

    # ============================================================
    #  HIGH-LEVEL API (compatible con IntentAgent anterior)
    # ============================================================

    def classify(self, message: str, context: str = "") -> IntentOutput:
        """Clasifica intención. Método principal que el Orchestrator llama."""
        input_data = IntentInput(message=message, context=context)
        return self.fallback(input_data)

    def classify_with_runner(self, runner: Any, message: str,
                             context: str = "") -> IntentOutput:
        """Clasifica usando AgentRunner (LLM → fallback fusionado)."""
        input_data = IntentInput(message=message, context=context)
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, IntentOutput):
            # Fusión: combinar resultado LLM con TF-IDF para calibrar confianza
            tfidf_result = self._cable_tfidf(message)
            llm_result = result.data
            return self._fuse_signals(tfidf_result, llm_result)

        return self.fallback(input_data)

    def to_intent_payload(self, output: IntentOutput, context: str = "") -> Any:
        """
        CABLE de compatibilidad: Convierte IntentOutput → IntentPayload
        para el pipeline existente (MacroRouter, APAPlanner, etc.).
        """
        from src.core.shared.contracts import IntentPayload, OperationType, GoalType

        op = output.operation if output.operation in VALID_OPERATIONS else OperationType.SEARCH
        goal = output.goal if output.goal in VALID_GOALS else GoalType.FEATURE_ADD

        scrap_query = ""
        if op in (OperationType.CREATE, OperationType.OPTIMIZE, OperationType.REFACTOR):
            scrap_query = f"modern {goal} {op} {output.language}"

        return IntentPayload(
            op=op,
            target=output.target or "unknown",
            goal=goal,
            scrap_query=scrap_query,
            confidence=output.confidence,
            language=output.language or "python",
            raw_code="",
            context=context,
        )
