"""
Scorer de memoria del Asistente.

Calcula la importancia de almacenar informacion
en memoria basado en heurísticas:
  - Tipo de contenido (preferencia > hecho > contexto)
  - Repeticion (mencionado multiples veces = importante)
  - Explicitud (el usuario lo pidio directamente)
  - Novedad (informacion nueva vs ya conocida)
"""

from __future__ import annotations

from typing import Any

from ...types.memory import MemoryEntry, MemoryCategory


# ─── Pesos por categoria ─────────────────────────────────────

_CATEGORY_WEIGHTS: dict[MemoryCategory, float] = {
    MemoryCategory.PREFERENCE: 0.9,    # Preferencias son muy importantes
    MemoryCategory.CORRECTION: 0.85,   # Correcciones del usuario
    MemoryCategory.FACT: 0.6,          # Hechos normales
    MemoryCategory.SKILL: 0.7,         # Habilidades
    MemoryCategory.CONTEXT: 0.3,       # Contexto temporal
    MemoryCategory.TOPIC: 0.4,         # Temas de conversacion
    MemoryCategory.EMOTION: 0.5,       # Estado emocional
}

# ─── Patrones de explicitud ──────────────────────────────────

_EXPLICIT_PATTERNS: list[str] = [
    "recuerda", "remember", "guarda", "save",
    "ten en cuenta", "keep in mind", "nota",
    "mi preferencia", "my preference",
    "siempre", "always", "nunca", "never",
    "prefiero", "i prefer",
]


class MemoryScorer:
    """
    Scorer de importancia de memoria.

    Calcula un score de 0.0 a 1.0 que indica si
    una pieza de informacion merece ser almacenada
    en memoria y por cuanto tiempo.
    """

    def score(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.FACT,
        existing_entries: list[MemoryEntry] | None = None,
    ) -> float:
        """
        Calcula el score de importancia.

        Formula: category_weight * 0.4
               + explicitness * 0.3
               + novelty * 0.2
               + repetition * 0.1
        """
        # 1. Peso de categoria
        cat_score = _CATEGORY_WEIGHTS.get(category, 0.5)

        # 2. Explicitud
        explicit = self._detect_explicitness(content)

        # 3. Novedad
        novelty = self._compute_novelty(content, existing_entries or [])

        # 4. Repeticion (ya mencionado antes = mas importante)
        repetition = self._compute_repetition(content, existing_entries or [])

        # Formula ponderada
        total = (
            cat_score * 0.4
            + explicit * 0.3
            + novelty * 0.2
            + repetition * 0.1
        )

        return min(total, 1.0)

    def should_store(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.FACT,
        threshold: float = 0.3,
        existing: list[MemoryEntry] | None = None,
    ) -> bool:
        """Verifica si el contenido merece ser almacenado."""
        return self.score(content, category, existing) >= threshold

    def compute_ttl(self, importance: float) -> float:
        """
        Calcula TTL en segundos basado en importancia.

        importance >= 0.8 → sin expiracion (0)
        importance >= 0.5 → 24 horas
        importance >= 0.3 → 4 horas
        importance < 0.3  → 1 hora
        """
        if importance >= 0.8:
            return 0.0       # Sin expiracion
        if importance >= 0.5:
            return 86400.0   # 24h
        if importance >= 0.3:
            return 14400.0   # 4h
        return 3600.0        # 1h

    # ─── Privados ─────────────────────────────────────────────

    @staticmethod
    def _detect_explicitness(content: str) -> float:
        """Detecta si el usuario es explicito sobre guardar."""
        content_lower = content.lower()
        for pattern in _EXPLICIT_PATTERNS:
            if pattern in content_lower:
                return 1.0
        return 0.2

    @staticmethod
    def _compute_novelty(content: str, existing: list[MemoryEntry]) -> float:
        """Computa la novedad del contenido vs lo existente."""
        if not existing:
            return 1.0

        content_lower = content.lower()
        content_words = set(content_lower.split())

        max_similarity = 0.0
        for entry in existing:
            entry_words = set(entry.content.lower().split())
            if not entry_words:
                continue
            overlap = len(content_words & entry_words)
            total = max(len(content_words), len(entry_words))
            similarity = overlap / total if total > 0 else 0.0
            max_similarity = max(max_similarity, similarity)

        # Novedad = 1 - similitud_maxima
        return max(0.0, 1.0 - max_similarity)

    @staticmethod
    def _compute_repetition(content: str, existing: list[MemoryEntry]) -> float:
        """Computa si el contenido ha sido mencionado antes."""
        if not existing:
            return 0.0

        content_lower = content.lower()
        mentions = sum(
            1 for e in existing
            if content_lower in e.content.lower()
        )

        if mentions >= 3:
            return 1.0
        if mentions >= 2:
            return 0.7
        if mentions >= 1:
            return 0.4
        return 0.0
