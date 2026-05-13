"""
CriticalityAgent — main class inheriting from mixins.
"""

import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from ._imports import (
    logger, BaseAgent, AgentResult, IntentOutput,
    CriticalityInput, CriticalityOutput,
    LEVEL_FAST, LEVEL_MODERATE, LEVEL_SURGICAL,
    STR_TO_LEVEL, LEVEL_TO_PATH,
    OP_CRITICALITY_MAP, GOAL_CRITICALITY_MAP,
    CRITICALITY_ADJUSTMENTS,
)
from ._signals_mixin import SignalsMixin


class CriticalityAgent(SignalsMixin, BaseAgent[CriticalityOutput]):
    """
    Agente F4: Ruteo Dinámico de Criticalidad.

    Unifica la inferencia de criticalidad desde múltiples señales:
    1. LLM (si Qwen disponible) — comprensión semántica profunda
    2. Semantic Engine — comparación con patrones conocidos
    3. Determinista Multi-Signal — fusión de keywords + AST + memory

    Produce CriticalityOutput canónico que alimenta:
    - F1 (DAG): path selection
    - F2 (Surgical): calibración de fusión
    - F3 (Context): modificación de presupuesto
    - CodeAgent: ajuste de generación
    - BusinessLogicAgent: ajuste de ejecución
    """

    def __init__(self, semantic_engine=None, smart_memory=None,
                 macro_router=None) -> None:
        super().__init__(name="criticality")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._macro_router = macro_router
        # Historial de criticalidad para retroalimentación
        self._history: List[Dict[str, Any]] = []
        self._history_max = 50

    def wire(self, semantic_engine=None, smart_memory=None,
             macro_router=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
        if macro_router is not None:
            self._macro_router = macro_router

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye prompt para inferencia LLM de criticalidad."""
        if isinstance(input_data, CriticalityInput):
            op = input_data.operation
            goal = input_data.goal
            target = input_data.target
            context = input_data.context
            code_snippet = input_data.code_snippet
        else:
            op = "SEARCH"
            goal = "FEATURE_ADD"
            target = ""
            context = str(input_data)[:200]
            code_snippet = ""

        system = (
            "You are a criticality assessment engine. "
            "Rate how CRITICAL this operation is on a 1-3 scale:\n"
            "1 = FAST_STANDARD: safe read-only, simple query, explain\n"
            "2 = DEEP_MODERATE: creates code, modifies files, API changes\n"
            "3 = SURGICAL_CRITICAL: auth, crypto, payments, DB migration, "
            "security-sensitive operations\n\n"
            "Reply with ONLY a JSON object:\n"
            '{"level":1|2|3,"reason":"...","confidence":0.0-1.0}'
        )
        user = (
            f"Op:{op} Goal:{goal} Target:{target[:100]} "
            f"Ctx:{context[:150]} Code:{code_snippet[:100]}"
        )
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[CriticalityOutput]:
        """Parsea la respuesta del LLM a un CriticalityOutput."""
        cleaned = self.clean_llm_text(raw_response)
        json_data = self.extract_json(cleaned)

        if json_data and isinstance(json_data, dict):
            level = json_data.get("level", 2)
            if isinstance(level, str):
                level = STR_TO_LEVEL.get(level.lower(), 2)
            level = max(1, min(3, int(level)))

            reason = str(json_data.get("reason", "LLM inference"))[:200]
            confidence = float(json_data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            adjustments = CRITICALITY_ADJUSTMENTS.get(level, CRITICALITY_ADJUSTMENTS[2])

            return CriticalityOutput(
                level=level,
                path=LEVEL_TO_PATH.get(level, "standard"),
                reason=reason,
                confidence=confidence,
                source="llm",
                adjustments=adjustments,
            )

        # Try to parse just a number
        num_match = re.search(r'[123]', cleaned)
        if num_match:
            level = int(num_match.group())
            adjustments = CRITICALITY_ADJUSTMENTS.get(level, CRITICALITY_ADJUSTMENTS[2])
            return CriticalityOutput(
                level=level,
                path=LEVEL_TO_PATH.get(level, "standard"),
                reason="LLM numeric response",
                confidence=0.4,
                source="llm",
                adjustments=adjustments,
            )

        return None

    def fallback(self, input_data: Any) -> CriticalityOutput:
        """
        Fallback determinista: Fusión Multi-Signal sin LLM.
        """
        start = time.time()

        if isinstance(input_data, CriticalityInput):
            op = input_data.operation
            goal = input_data.goal
            target = input_data.target
            context = input_data.context
            code_snippet = input_data.code_snippet
            existing_level = input_data.existing_level
        else:
            op = "SEARCH"
            goal = "FEATURE_ADD"
            target = ""
            context = str(input_data)[:200]
            code_snippet = ""
            existing_level = None

        # ── Open Design Visual Bypass ──
        # If the request contains UI/visual keywords, force FAST (level 1)
        # to skip Z3/AC-3 solver verification for frontend generation
        from ._imports import UI_VISUAL_KEYWORDS, VISUAL_BYPASS_REASON
        combined_lower = f"{target} {context} {code_snippet}".lower()
        visual_matches = [kw for kw in UI_VISUAL_KEYWORDS if kw in combined_lower]
        if len(visual_matches) >= 2:  # At least 2 UI keywords → visual bypass
            level = 1  # FAST_STANDARD
            adjustments = CRITICALITY_ADJUSTMENTS.get(1, CRITICALITY_ADJUSTMENTS[2])
            self._record_history(op, goal, target, level)
            return CriticalityOutput(
                level=level,
                path=LEVEL_TO_PATH.get(level, "low_crit"),
                reason=f"{VISUAL_BYPASS_REASON} (keywords: {', '.join(visual_matches[:3])})",
                confidence=0.95,
                source="visual_bypass",
                adjustments=adjustments,
            )

        # ── Signal 1: Keyword analysis ──
        combined_text = f"{target} {context} {code_snippet}".lower()
        keyword_level = self._keyword_signal(combined_text)

        # ── Signal 2: Operation/Goal baseline ──
        op_level = OP_CRITICALITY_MAP.get(op, 1)
        goal_level = GOAL_CRITICALITY_MAP.get(goal, 1)
        baseline_level = max(op_level, goal_level)

        # ── Signal 3: SmartMemory importance ──
        memory_level = self._memory_signal(target, op, goal)

        # ── Signal 4: MacroRouter AST topology ──
        router_level = self._router_signal(target)

        # ── Signal 5: Historical pattern ──
        history_level = self._history_signal(op, target)

        # ── Fusión ponderada ──
        signals = [
            (keyword_level, 0.30),
            (baseline_level, 0.25),
            (router_level, 0.20),
            (memory_level, 0.15),
            (history_level, 0.10),
        ]

        weighted_sum = sum(level * weight for level, weight in signals)
        total_weight = sum(w for _, w in signals)
        fused = weighted_sum / total_weight if total_weight > 0 else 2.0

        # Redondear al entero más cercano, con sesgo hacia arriba por seguridad
        level = min(3, max(1, int(fused + 0.4)))

        # Si hay una señal existente del MacroRouter, no bajar su nivel
        if existing_level is not None:
            existing_int = STR_TO_LEVEL.get(str(existing_level).lower(),
                                            int(existing_level) if str(existing_level).isdigit() else 1)
            level = max(level, existing_int)

        # Generar razón explicativa
        reason = self._build_reason(level, keyword_level, baseline_level,
                                     router_level, memory_level, history_level)
        adjustments = CRITICALITY_ADJUSTMENTS.get(level, CRITICALITY_ADJUSTMENTS[2])
        confidence = self._compute_confidence(signals, level)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        # Registrar en historial para retroalimentación
        self._record_history(op, goal, target, level)

        return CriticalityOutput(
            level=level,
            path=LEVEL_TO_PATH.get(level, "standard"),
            reason=reason,
            confidence=confidence,
            source="fallback",
            adjustments=adjustments,
        )

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def assess_with_runner(self, runner: Any, intent_output: Any,
                           message: str = "",
                           existing_criticality: Any = None) -> CriticalityOutput:
        """Evalúa criticalidad usando AgentRunner (LLM → fallback)."""
        # Normalizar existing_criticality a int
        existing_int = None
        if existing_criticality is not None:
            try:
                existing_int = STR_TO_LEVEL.get(
                    str(existing_criticality).lower(),
                    int(float(existing_criticality)),
                )
            except (ValueError, TypeError):
                existing_int = None

        # Extraer información del intent_output
        if isinstance(intent_output, IntentOutput):
            op = intent_output.operation
            goal = intent_output.goal
            target = intent_output.target
        elif intent_output and hasattr(intent_output, 'op'):
            op = getattr(intent_output, 'op', 'SEARCH')
            goal = getattr(intent_output, 'goal', 'FEATURE_ADD')
            target = getattr(intent_output, 'target', '')
        else:
            op = "SEARCH"
            goal = "FEATURE_ADD"
            target = ""

        # ── Open Design Visual Bypass (pre-LLM check) ──
        from ._imports import UI_VISUAL_KEYWORDS, VISUAL_BYPASS_REASON
        check_text = f"{target} {message[:200]}".lower()
        visual_matches = [kw for kw in UI_VISUAL_KEYWORDS if kw in check_text]
        if len(visual_matches) >= 2:
            level = 1
            adjustments = CRITICALITY_ADJUSTMENTS.get(1, CRITICALITY_ADJUSTMENTS[2])
            self._record_history(op, goal, target, level)
            return CriticalityOutput(
                level=level,
                path=LEVEL_TO_PATH.get(level, "low_crit"),
                reason=f"{VISUAL_BYPASS_REASON} (keywords: {', '.join(visual_matches[:3])})",
                confidence=0.95,
                source="visual_bypass",
                adjustments=adjustments,
            )

        input_data = CriticalityInput(
            operation=op,
            goal=goal,
            target=target,
            context=message[:300],
            code_snippet="",
            existing_level=existing_int,
        )

        # Intentar LLM si runner disponible
        if runner:
            try:
                result: AgentResult = runner.run(self, input_data)
                if result.success and isinstance(result.data, CriticalityOutput):
                    if existing_int is not None and result.data.level < existing_int:
                        result.data.level = existing_int
                        result.data.path = LEVEL_TO_PATH.get(existing_int, "standard")
                        result.data.adjustments = CRITICALITY_ADJUSTMENTS.get(
                            existing_int, CRITICALITY_ADJUSTMENTS[2]
                        )
                        result.data.reason += " (elevated by MacroRouter signal)"
                    self._record_history(op, goal, target, result.data.level)
                    return result.data
            except Exception as e:
                logger.debug(f"CriticalityAgent LLM failed: {e}")

        # Fallback determinista
        return self.fallback(input_data)

    def assess_deterministic(self, operation: str, goal: str,
                             target: str = "", context: str = "",
                             existing_criticality: Any = None) -> CriticalityOutput:
        """Evaluación determinista directa (sin LLM)."""
        existing_int = None
        if existing_criticality is not None:
            existing_int = STR_TO_LEVEL.get(
                str(existing_criticality).lower(),
                int(existing_criticality) if str(existing_criticality).isdigit() else None
            )

        input_data = CriticalityInput(
            operation=operation,
            goal=goal,
            target=target,
            context=context[:300],
            existing_level=existing_int,
        )
        return self.fallback(input_data)

    @staticmethod
    def normalize_criticality(raw_value: Any) -> int:
        """
        Normaliza cualquier formato de criticalidad a int (1/2/3).
        """
        if raw_value is None:
            return LEVEL_MODERATE

        if isinstance(raw_value, int):
            return max(1, min(3, raw_value))

        return STR_TO_LEVEL.get(str(raw_value).lower(), LEVEL_MODERATE)

    @staticmethod
    def level_to_path(level: int) -> str:
        """Convierte nivel de criticalidad a DAG path."""
        return LEVEL_TO_PATH.get(level, "standard")
