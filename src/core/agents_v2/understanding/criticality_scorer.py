"""
A04 CriticalityScorer — SINGLE RESPONSIBILITY: Compute criticality level (1/2/3).

5 weighted signals → weighted sum → round up (safety bias).
Deterministic. No AI.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from ..resilience import BaseAgent
from ..schemas import IntentResult, TargetResult, CriticalityResult

# ──────────────────────────────────────────────────────────────
# CRITICALITY CONSTANTS
# ──────────────────────────────────────────────────────────────

CRITICAL_KEYWORDS = [
    "auth", "password", "token", "secret", "crypto", "encrypt", "decrypt",
    "payment", "stripe", "credit", "bank", "transaction", "money",
    "security", "vulnerability", "exploit", "injection", "xss",
    "migration", "drop", "alter", "production",
    # Spanish
    "autenticar", "contrasena", "secreto", "pago", "seguridad",
    "vulnerabilidad", "produccion",
]

MODERATE_KEYWORDS = [
    "database", "db", "sql", "api", "config", "settings",
    "deploy", "server", "endpoint", "webhook",
    # Spanish
    "base de datos", "configuracion", "desplegar", "servidor",
]

# Operation → baseline criticality
OP_CRITICALITY = {
    "CREATE": 2, "REFACTOR": 2, "DELETE": 3, "SEARCH": 1,
    "ANALYZE": 1, "EXPLAIN": 1, "DEBUG": 2, "OPTIMIZE": 2,
}

# Goal → baseline criticality
GOAL_CRITICALITY = {
    "COMPLEXITY_REDUCTION": 1, "MODERN_PATTERN": 1, "BUG_FIX": 2,
    "FEATURE_ADD": 2, "SECURITY_HARDEN": 3, "PERFORMANCE": 2, "READABILITY": 1,
}

# UI/Visual keywords → force Level 1
VISUAL_KEYWORDS = [
    "ui", "ux", "frontend", "css", "html", "design", "layout", "style",
    "button", "form", "modal", "dialog", "responsive", "animation",
    "interfaz", "diseno", "estilo", "boton", "formulario",
]

# Signal weights
SIGNAL_WEIGHTS = {
    "keyword": 0.30,
    "baseline": 0.25,
    "importance": 0.15,
    "router": 0.20,
    "history": 0.10,
}


class CriticalityScorer(BaseAgent[CriticalityResult]):
    """
    A04: Compute criticality level.

    Single Responsibility: Criticality scoring ONLY.
    Method: 5 weighted signals → fusion → level.
    Fallback: Default to Level 2 (DEEP_MODERATE) — errs on caution.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A04_CriticalityScorer", **kwargs)
        self._history: list[dict] = []
        self._history_lock = threading.Lock()

    def execute(self, input_data: Any) -> CriticalityResult:
        """
        Compute criticality from intent + target.

        input_data should be a dict with:
          - 'intent_result': IntentResult
          - 'target_result': TargetResult
          - 'message': original message (optional)
          - 'memory_importance': float 0-1 (optional)
          - 'existing_level': int (optional, from MacroRouter)
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        intent = input_data.get("intent_result")
        target = input_data.get("target_result")
        message = input_data.get("message", "")
        memory_importance = input_data.get("memory_importance", 0.5)
        existing_level = input_data.get("existing_level", 0)

        # Visual bypass
        if self._check_visual_bypass(message):
            return CriticalityResult(
                level=1,
                path="fast_standard",
                reason="Visual/UI content — skip deep verification",
                confidence=0.9,
                adjustments={"visual_bypass": True},
                source="deterministic",
            )

        # Compute 5 signals
        kw_signal = self._keyword_signal(message)
        baseline_signal = self._baseline_signal(intent)
        importance_signal = self._importance_signal(memory_importance)
        router_signal = self._router_signal(target)
        history_signal = self._history_signal(intent, target)

        # Weighted fusion
        fused = (
            kw_signal * SIGNAL_WEIGHTS["keyword"]
            + baseline_signal * SIGNAL_WEIGHTS["baseline"]
            + importance_signal * SIGNAL_WEIGHTS["importance"]
            + router_signal * SIGNAL_WEIGHTS["router"]
            + history_signal * SIGNAL_WEIGHTS["history"]
        )

        # Round up with safety bias
        level = min(int(fused + 0.4), 3)
        level = max(level, 1)

        # Never downgrade below existing level
        if existing_level > 0:
            level = max(level, existing_level)

        # Confidence based on signal agreement
        signals = [kw_signal, baseline_signal, importance_signal, router_signal, history_signal]
        confidence = self._compute_confidence(signals, level)

        # Build adjustments
        adjustments = self._build_adjustments(level)

        # Record history
        self._record_history(intent, target, level)

        path = {1: "fast_standard", 2: "deep_moderate", 3: "surgical_critical"}[level]

        return CriticalityResult(
            level=level,
            path=path,
            reason=f"Weighted fusion: kw={kw_signal:.1f} base={baseline_signal:.1f} "
                   f"imp={importance_signal:.1f} router={router_signal:.1f} hist={history_signal:.1f}",
            confidence=round(confidence, 2),
            adjustments=adjustments,
            source="deterministic",
        )

    def _keyword_signal(self, text: str) -> float:
        """Signal 1: Keyword analysis (0.30 weight)."""
        text_lower = text.lower()
        critical_hits = sum(1 for kw in CRITICAL_KEYWORDS if kw in text_lower)
        moderate_hits = sum(1 for kw in MODERATE_KEYWORDS if kw in text_lower)

        if critical_hits >= 2:
            return 3.0
        elif critical_hits >= 1:
            return 2.5
        elif moderate_hits >= 2:
            return 2.0
        elif moderate_hits >= 1:
            return 1.5
        return 1.0

    def _baseline_signal(self, intent: Any) -> float:
        """Signal 2: Operation/Goal baseline (0.25 weight)."""
        if not intent or not isinstance(intent, IntentResult):
            return 2.0
        op_level = OP_CRITICALITY.get(intent.operation, 2)
        goal_level = GOAL_CRITICALITY.get(intent.goal, 2)
        return (op_level + goal_level) / 2.0

    def _importance_signal(self, importance: float) -> float:
        """Signal 3: Memory importance (0.15 weight)."""
        if importance >= 0.8:
            return 3.0
        elif importance >= 0.5:
            return 2.0
        return 1.0

    def _router_signal(self, target: Any) -> float:
        """Signal 4: Router/AST signal (0.20 weight)."""
        if not target or not isinstance(target, TargetResult):
            return 1.0
        # Check target file for security-related names
        if target.target_file:
            name = target.target_file.lower()
            if any(kw in name for kw in ["auth", "security", "payment", "crypto"]):
                return 3.0
            elif any(kw in name for kw in ["api", "db", "config"]):
                return 2.0
        return 1.0

    def _history_signal(self, intent: Any, target: Any) -> float:
        """Signal 5: Historical patterns (0.10 weight)."""
        with self._history_lock:
            if not self._history:
                return 2.0  # Default moderate when no history
            recent = self._history[-10:]
            avg_level = sum(h.get("level", 2) for h in recent) / len(recent)
        return avg_level

    def _check_visual_bypass(self, text: str) -> bool:
        """Force Level 1 for UI/visual content."""
        if not text:
            return False
        text_lower = text.lower()
        count = sum(1 for kw in VISUAL_KEYWORDS if kw in text_lower)
        return count >= 2

    def _compute_confidence(self, signals: list[float], final_level: int) -> float:
        """Compute confidence from signal agreement."""
        if not signals:
            return 0.5
        agree = sum(1 for s in signals if abs(s - final_level) <= 0.5)
        ratio = agree / len(signals)
        return max(0.2, min(0.2 + ratio * 0.8, 0.99))

    def _build_adjustments(self, level: int) -> dict:
        """Build downstream adjustments based on level."""
        adj: dict[str, Any] = {}
        if level >= 2:
            adj["audit_trail"] = True
            adj["extra_validation"] = True
        if level >= 3:
            adj["integrity_check"] = True
            adj["cross_reference"] = True
            adj["rollback"] = True
            adj["defensive_injection"] = True
            adj["validation_layers"] = 3
            adj["idempotency_check"] = True
        return adj

    def _record_history(self, intent: Any, target: Any, level: int) -> None:
        op = intent.operation if intent and isinstance(intent, IntentResult) else ""
        with self._history_lock:
            self._history.append({"operation": op, "level": level})
            if len(self._history) > 50:
                self._history = self._history[-50:]

    def fallback(self, input_data: Any) -> CriticalityResult:
        """Safe default: Level 2 (DEEP_MODERATE) — errs on caution."""
        return CriticalityResult(
            level=2,
            path="deep_moderate",
            reason="Fallback: defaulting to moderate caution",
            confidence=0.3,
            adjustments={"audit_trail": True},
            source="fallback",
        )
