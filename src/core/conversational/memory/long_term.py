"""
Long-Term Memory del Asistente.

Memoria persistente entre sesiones. Almacena hechos,
preferencias y patrones aprendidos del usuario.

Caracteristicas:
  - Persistencia entre sesiones (in-memory con futuro DB)
  - Scoring avanzado con decay temporal
  - Promocion automatica desde short-term
  - Busqueda semantica simplificada (keyword-based)
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ...types.base import Result, Ok
from ...types.memory import (
    MemoryEntry, MemoryQuery, MemoryResult,
    MemoryType, MemoryCategory, MemoryStats,
)
from ...config.constants import (
    MEMORY_MAX_LONG_TERM,
    MEMORY_IMPORTANCE_THRESHOLD,
)


class LongTermMemory:
    """
    Long-Term Memory: conocimiento persistente.

    Almacena entradas promovidas desde short-term
    cuando su importancia supera el umbral.
    """

    def __init__(
        self,
        max_entries: int = MEMORY_MAX_LONG_TERM,
        importance_threshold: float = MEMORY_IMPORTANCE_THRESHOLD,
    ) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._tag_index: dict[str, list[str]] = {}
        self._category_index: dict[MemoryCategory, list[str]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._importance_threshold = importance_threshold
        self._stats = MemoryStats()

    # ─── Promocion ────────────────────────────────────────────

    def should_promote(self, entry: MemoryEntry) -> bool:
        """Verifica si una entrada merece promocion a LTM."""
        if entry.importance < self._importance_threshold:
            return False
        if entry.category in (
            MemoryCategory.PREFERENCE,
            MemoryCategory.FACT,
            MemoryCategory.SKILL,
            MemoryCategory.CORRECTION,
        ):
            return True
        return entry.importance >= 0.9  # Muy importante

    def promote(self, entry: MemoryEntry) -> Result[bool]:
        """Promueve una entrada desde short-term a long-term."""
        if not self.should_promote(entry):
            return Ok(False)

        with self._lock:
            # Crear copia como long-term
            ltm_entry = MemoryEntry(
                content=entry.content,
                category=entry.category,
                memory_type=MemoryType.LONG_TERM,
                session_id="",  # LTM no esta ligada a sesion
                importance=entry.importance,
                tags=entry.tags,
                source=entry.source,
                metadata=entry.metadata,
            )

            # Eviction si es necesario
            while len(self._entries) >= self._max_entries:
                self._evict_lowest()

            self._entries[ltm_entry.memory_id] = ltm_entry

            # Indexar por tags
            for tag in ltm_entry.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(ltm_entry.memory_id)

            # Indexar por categoria
            cat = ltm_entry.category
            if cat not in self._category_index:
                self._category_index[cat] = []
            self._category_index[cat].append(ltm_entry.memory_id)

            self._stats.long_term_count = len(self._entries)
            self._stats.total_stored += 1

            return Ok(True)

    # ─── Retrieve ─────────────────────────────────────────────

    def retrieve(self, query: MemoryQuery) -> MemoryResult:
        """Busca en la memoria de largo plazo."""
        start = time.time()

        with self._lock:
            candidates: list[MemoryEntry] = []

            # Filtrar por categorias si se especifican
            if query.categories:
                ids: list[str] = []
                for cat in query.categories:
                    ids.extend(self._category_index.get(cat, []))
                candidates = [
                    self._entries[mid]
                    for mid in set(ids)
                    if mid in self._entries
                ]
            else:
                candidates = list(self._entries.values())

            # Filtrar por tags
            if query.tags:
                tag_ids: list[str] = []
                for tag in query.tags:
                    tag_ids.extend(self._tag_index.get(tag, []))
                tag_set = set(tag_ids)
                candidates = [
                    e for e in candidates
                    if e.memory_id in tag_set
                ]

            # Filtrar por importancia
            if query.min_importance > 0:
                candidates = [
                    e for e in candidates
                    if e.importance >= query.min_importance
                ]

            # Scoring
            for entry in candidates:
                entry.relevance_score = self._score(entry, query)
                entry.touch()

            candidates.sort(key=lambda e: e.relevance_score, reverse=True)
            results = candidates[:query.max_results]

        elapsed = (time.time() - start) * 1000
        self._stats.total_retrieved += 1
        self._stats.avg_retrieval_ms = (
            (self._stats.avg_retrieval_ms + elapsed) / 2
        )

        return MemoryResult(
            entries=results,
            total_matches=len(candidates),
            query=query,
            search_time_ms=elapsed,
        )

    # ─── Management ───────────────────────────────────────────

    def decay_all(self, factor: float = 0.99) -> int:
        """Aplica decay a todas las entradas. Retorna las removidas."""
        with self._lock:
            removed = 0
            to_remove: list[str] = []

            for mid, entry in self._entries.items():
                entry.decay_importance(factor)
                if entry.importance < 0.1:
                    to_remove.append(mid)

            for mid in to_remove:
                self._remove_entry(mid)
                removed += 1

            self._stats.long_term_count = len(self._entries)
            self._stats.evictions += removed
            return removed

    @property
    def stats(self) -> MemoryStats:
        """Estadisticas de long-term memory."""
        self._stats.long_term_count = len(self._entries)
        return self._stats

    # ─── Privados ─────────────────────────────────────────────

    def _evict_lowest(self) -> None:
        """Evicta la entrada con menor importancia."""
        if not self._entries:
            return
        min_id = min(
            self._entries,
            key=lambda mid: self._entries[mid].importance,
        )
        self._remove_entry(min_id)

    def _remove_entry(self, mid: str) -> None:
        """Remueve una entrada y limpia indices."""
        entry = self._entries.pop(mid, None)
        if entry:
            for tag in entry.tags:
                if tag in self._tag_index:
                    self._tag_index[tag] = [
                        i for i in self._tag_index[tag] if i != mid
                    ]
            cat = entry.category
            if cat in self._category_index:
                self._category_index[cat] = [
                    i for i in self._category_index[cat] if i != mid
                ]

    @staticmethod
    def _score(entry: MemoryEntry, query: MemoryQuery) -> float:
        """Score de relevancia para long-term."""
        score = 0.0

        # Importance es clave en LTM
        score += entry.importance * 0.5

        # Keyword overlap
        if query.text:
            query_words = set(query.text.lower().split())
            entry_words = set(entry.content.lower().split())
            overlap = len(query_words & entry_words)
            total = max(len(query_words), 1)
            score += (overlap / total) * 0.3

        # Category match
        if query.categories and entry.category in query.categories:
            score += 0.1

        # Tag match
        if query.tags:
            tag_overlap = len(set(query.tags) & set(entry.tags))
            score += min(tag_overlap * 0.05, 0.1)

        # Access frequency
        score += min(entry.access_count * 0.02, 0.1)

        return min(score, 1.0)
