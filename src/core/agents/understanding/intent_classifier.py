"""
A01 IntentClassifier — SINGLE RESPONSIBILITY: Classify user intent into (operation, goal).

Deterministic keyword scoring. No AI.
Uses weighted keyword matching (word match = 2pts, substring = 1pt).
Supports bilingual EN/ES keywords.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import IntentResult

# ──────────────────────────────────────────────────────────────
# VALID OPERATIONS & GOALS
# ──────────────────────────────────────────────────────────────

VALID_OPERATIONS = frozenset({
    "CREATE", "REFACTOR", "DELETE", "SEARCH",
    "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE",
})

VALID_GOALS = frozenset({
    "COMPLEXITY_REDUCTION", "MODERN_PATTERN", "BUG_FIX",
    "FEATURE_ADD", "SECURITY_HARDEN", "PERFORMANCE", "READABILITY",
})

# Bilingual keyword maps (EN + ES)
OP_KEYWORDS: dict[str, list] = {
    "CREATE": [
        "create", "build", "generate", "make", "add", "new", "implement",
        "crear", "construir", "generar", "hacer", "agregar", "nuevo", "implementar",
    ],
    "REFACTOR": [
        "refactor", "restructure", "reorganize", "clean", "rewrite",
        "refactorizar", "reestructurar", "reorganizar", "limpiar", "reescribir",
    ],
    "DELETE": [
        "delete", "remove", "erase", "drop", "clear", "destroy",
        "eliminar", "borrar", "quitar", "destruir",
    ],
    "SEARCH": [
        "search", "find", "lookup", "query", "filter", "locate",
        "buscar", "encontrar", "consultar", "filtrar", "localizar",
    ],
    "ANALYZE": [
        "analyze", "review", "examine", "inspect", "assess", "evaluate",
        "analizar", "revisar", "examinar", "inspeccionar", "evaluar",
    ],
    "EXPLAIN": [
        "explain", "describe", "clarify", "understand", "what is",
        "explicar", "describir", "aclarar", "entender", "que es",
    ],
    "DEBUG": [
        "debug", "fix", "troubleshoot", "error", "bug", "issue", "problem",
        "depurar", "corregir", "solucionar", "error", "fallo", "problema",
    ],
    "OPTIMIZE": [
        "optimize", "improve", "enhance", "speed up", "performance",
        "optimizar", "mejorar", "acelerar", "rendimiento",
    ],
}

GOAL_KEYWORDS: dict[str, list] = {
    "COMPLEXITY_REDUCTION": [
        "simplify", "reduce complexity", "clean up", "less complex",
        "simplificar", "reducir complejidad", "limpiar",
    ],
    "MODERN_PATTERN": [
        "modernize", "update pattern", "latest", "best practice",
        "modernizar", "actualizar", "mejor practica",
    ],
    "BUG_FIX": [
        "fix bug", "patch", "hotfix", "bugfix", "resolve error",
        "corregir fallo", "parche", "solucionar error",
    ],
    "FEATURE_ADD": [
        "add feature", "new feature", "implement", "extend",
        "agregar funcion", "nueva funcion", "implementar", "extender",
    ],
    "SECURITY_HARDEN": [
        "security", "secure", "vulnerability", "encrypt", "auth",
        "seguridad", "seguro", "vulnerabilidad", "encriptar", "autenticar",
    ],
    "PERFORMANCE": [
        "performance", "fast", "speed", "optimize", "efficient",
        "rendimiento", "rapido", "velocidad", "eficiente",
    ],
    "READABILITY": [
        "readability", "readable", "clean code", "documentation",
        "legibilidad", "legible", "codigo limpio", "documentacion",
    ],
}


class IntentClassifier(BaseAgent[IntentResult]):
    """
    A01: Classify user intent into (operation, goal).

    Single Responsibility: Intent classification ONLY.
    Method: Weighted keyword scoring (deterministic).
    Fallback: Default to SEARCH + FEATURE_ADD with low confidence.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A01_IntentClassifier", **kwargs)
        # Pre-compile keyword patterns for performance
        self._op_patterns = self._build_patterns(OP_KEYWORDS)
        self._goal_patterns = self._build_patterns(GOAL_KEYWORDS)

    @staticmethod
    def _build_patterns(keywords: dict[str, list]) -> dict[str, list]:
        """Pre-compile regex patterns for keyword matching."""
        patterns = {}
        for key, kws in keywords.items():
            compiled = []
            for kw in kws:
                # Word boundary match
                compiled.append(re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE))
            patterns[key] = (kws, compiled)
        return patterns

    def execute(self, input_data: Any) -> IntentResult:
        """
        Classify intent using keyword scoring.

        Scoring: word boundary match = 2pts, substring match = 1pt.
        Returns the highest-scoring operation and goal.
        """
        text = str(input_data).lower() if input_data else ""
        if not text:
            return self.fallback(input_data)

        # Score operations
        best_op, op_score = self._score_category(text, self._op_patterns, "SEARCH")
        # Score goals
        best_goal, goal_score = self._score_category(text, self._goal_patterns, "FEATURE_ADD")

        # op_score and goal_score are each 0-1 normalized, so average is also 0-1.
        # The max() ensures a minimum confidence floor for downstream agents.
        confidence = max((op_score + goal_score) / 2.0, 0.1)

        return IntentResult(
            operation=best_op,
            goal=best_goal,
            confidence=round(confidence, 2),
            source="deterministic",
            evidence={
                "op_score": op_score,
                "goal_score": goal_score,
                "best_op": best_op,
                "best_goal": best_goal,
            },
        )

    def _score_category(
        self, text: str, patterns: dict, default: str
    ) -> tuple:
        """Score text against keyword patterns, return (best_key, score)."""
        scores: dict[str, float] = {}

        for key, (kws, compiled) in patterns.items():
            score = 0.0
            for kw, pattern in zip(kws, compiled):
                # Word boundary match (2pts)
                if pattern.search(text):
                    score += 2.0
                # Substring match (1pt)
                elif kw.lower() in text:
                    score += 1.0
            if score > 0:
                scores[key] = score

        if not scores:
            return default, 0.1

        best = max(scores, key=scores.get)
        max_score = scores[best]
        # Normalize to 0-1 range
        normalized = min(max_score / 6.0, 1.0)
        return best, normalized

    def fallback(self, input_data: Any) -> IntentResult:
        """Safe default: SEARCH + FEATURE_ADD with low confidence."""
        return IntentResult(
            operation="SEARCH",
            goal="FEATURE_ADD",
            confidence=0.1,
            source="fallback",
        )
