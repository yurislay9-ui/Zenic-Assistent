"""
Signal methods mixin for CriticalityAgent (Multi-Signal Fusion).
"""

import time
import logging
from typing import Any, Dict, List, Tuple

from ._imports import (
    logger,
    LEVEL_FAST, LEVEL_MODERATE, LEVEL_SURGICAL,
    CRITICAL_KEYWORDS, MODERATE_KEYWORDS,
)


class SignalsMixin:
    """Mixin with signal methods for multi-signal criticality fusion."""

    # ============================================================
    #  SIGNAL METHODS (Multi-Signal Fusion)
    # ============================================================

    def _keyword_signal(self, combined_text: str) -> int:
        """Señal 1: Análisis de keywords críticos en texto combinado."""
        critical_hits = sum(1 for kw in CRITICAL_KEYWORDS if kw in combined_text)
        moderate_hits = sum(1 for kw in MODERATE_KEYWORDS if kw in combined_text)

        if critical_hits >= 2:
            return LEVEL_SURGICAL
        elif critical_hits >= 1:
            return LEVEL_MODERATE  # One critical keyword = at least moderate
        elif moderate_hits >= 2:
            return LEVEL_MODERATE
        elif moderate_hits >= 1:
            return max(LEVEL_FAST, LEVEL_MODERATE - 1)
        return LEVEL_FAST

    def _memory_signal(self, target: str, op: str, goal: str) -> int:
        """Señal 3: SmartMemory importance score."""
        if not self._smart_memory:
            return LEVEL_MODERATE  # Sin memoria → asumir moderado

        try:
            from src.core.smart_memory import SmartMemory
            importance = SmartMemory.compute_importance(
                target or "unknown", op, goal, success=True, response_length=0
            )
            # importance 0-1: mapear a criticalidad
            if importance >= 0.7:
                return LEVEL_SURGICAL
            elif importance >= 0.4:
                return LEVEL_MODERATE
            return LEVEL_FAST
        except Exception:
            return LEVEL_MODERATE

    def _router_signal(self, target: str) -> int:
        """Señal 4: MacroRouter AST topology check."""
        if not self._macro_router:
            return LEVEL_FAST

        try:
            # Crear un IntentPayload temporal para consultar MacroRouter
            from src.core.shared.contracts import IntentPayload, CriticalityLevel
            temp_intent = IntentPayload(target=target or "unknown")
            routing = self._macro_router.route(temp_intent)
            return routing.criticality
        except Exception:
            return LEVEL_FAST

    def _history_signal(self, op: str, target: str) -> int:
        """Señal 5: Patrones históricos de criticalidad."""
        if not self._history:
            return LEVEL_FAST

        target_lower = (target or "").lower()
        matching = [
            h for h in self._history
            if h.get("op") == op or target_lower in h.get("target", "").lower()
        ]

        if not matching:
            return LEVEL_FAST

        avg_level = sum(h.get("level", 1) for h in matching) / len(matching)
        return min(3, max(1, int(avg_level + 0.5)))

    def _compute_confidence(self, signals: List[Tuple[int, float]],
                            final_level: int) -> float:
        """Computa confianza basada en concordancia de señales."""
        if not signals:
            return 0.3

        # Contar señales que concuerdan con el nivel final
        agreeing = sum(1 for level, _ in signals if level == final_level)
        total = len(signals)
        agreement_ratio = agreeing / total if total > 0 else 0

        # Más señales que concuerdan → más confianza
        confidence = 0.3 + (agreement_ratio * 0.6)

        # Si todas concuerdan, confianza muy alta
        if agreement_ratio == 1.0:
            confidence = 0.95

        return max(0.2, min(0.99, confidence))

    def _build_reason(self, level: int, kw: int, baseline: int,
                      router: int, memory: int, history: int) -> str:
        """Construye razón explicativa de la criticalidad."""
        level_names = {1: "FAST_STANDARD", 2: "DEEP_MODERATE", 3: "SURGICAL_CRITICAL"}
        parts = [f"Level {level} ({level_names.get(level, 'UNKNOWN')})"]

        signals = {
            "keyword": kw, "baseline": baseline, "router": router,
            "memory": memory, "history": history,
        }
        elevating = [k for k, v in signals.items() if v >= level]
        if elevating:
            parts.append(f"elevated by: {', '.join(elevating)}")

        if level == 3:
            parts.append("Full pipeline + Z3 solver + security checks required")
        elif level == 2:
            parts.append("Standard pipeline with validation")
        else:
            parts.append("Fast path, minimal overhead")

        return ". ".join(parts)

    def _record_history(self, op: str, goal: str, target: str,
                        level: int) -> None:
        """Registra evaluación en historial para retroalimentación."""
        self._history.append({
            "op": op, "goal": goal, "target": target[:100],
            "level": level, "timestamp": time.time(),
        })
        # Mantener historial acotado
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max:]
