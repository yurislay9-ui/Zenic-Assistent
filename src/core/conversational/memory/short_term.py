"""
Short-Term Memory del Asistente.

Memoria de sesion: almacena datos, preferencias y contexto
de la sesion actual. Se pierde al cerrar la sesion.

Caracteristicas:
  - Indexado por session_id + category
  - Scoring de relevancia por frecuencia y recency
  - Auto-limpieza de entradas expiradas
  - Thread-safe
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ..types.base import Result, Ok
from ..types.memory import (
    MemoryEntry, MemoryQuery, MemoryResult,
    MemoryType, MemoryCategory, MemoryStats,
)
from ..config.constants import MEMORY_MAX_LONG_TERM


class ShortTermMemory:
    """
    Short-Term Memory: datos de la sesion actual.

    Almacena preferencias, hechos y contexto que
    es relevante solo durante la sesion activa.
    """

    def __init__(self, max_entries: int = MEMORY_MAX_LONG_TERM) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._session_index: dict[str, list[str]] = {}
        self._category_index: dict[MemoryCategory, list[str]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._stats = MemoryStats()

    # ─── Store ────────────────────────────────────────────────

    def store(self, entry: MemoryEntry) -> Result[bool, Exception]:
        """Almacena una entrada en short-term memory."""
        with self._lock:
            # Eviction si es necesario
            if len(self._entries) >= self._max_entries:
                self._evict_low_importance()

            # Marcar tipo
            entry.memory_type = MemoryType.SHORT_TERM

            # Si ya existe con mismo ID, actualizar
            if entry.memory_id in self._entries:
                self._entries[entry.memory_id] = entry
            else:
                self._entries[entry.memory_id] = entry

                # Indexar por sesion
                sid = entry.session_id
                if sid not in self._session_index:
                    self._session_index[sid] = []
                self._session_index[sid].append(entry.memory_id)

                # Indexar por categoria
                cat = entry.category
                if cat not in self._category_index:
                    self._category_index[cat] = []
                self._category_index[cat].append(entry.memory_id)

            self._stats.short_term_count = len(self._entries)
            self._stats.total_stored += 1

            return Ok(True)

    # ─── Retrieve ─────────────────────────────────────────────

    def retrieve(self, query: MemoryQuery) -> MemoryResult:
        """Busca entradas que matcheen la query."""
        start = time.time()

        with self._lock:
            candidates: list[MemoryEntry] = []

            # Filtrar por sesion si se especifica
            if query.session_id and query.session_id in self._session_index:
                ids = self._session_index[query.session_id]
                candidates = [
                    self._entries[mid]
                    for mid in ids
                    if mid in self._entries
                    and not self._entries[mid].is_expired
                ]
            else:
                candidates = [
                    e for e in self._entries.values()
                    if not e.is_expired
                ]

            # Filtrar por categorias
            if query.categories:
                candidates = [
                    e for e in candidates
                    if e.category in query.categories
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

            # Ordenar y limitar
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

    def get_session_entries(self, session_id: str) -> list[MemoryEntry]:
        """Obtiene todas las entradas de una sesion."""
        with self._lock:
            ids = self._session_index.get(session_id, [])
            return [
                self._entries[mid]
                for mid in ids
                if mid in self._entries
            ]

    def get_preferences(self, session_id: str) -> dict[str, Any]:
        """Obtiene preferencias almacenadas de una sesion."""
        entries = self.get_session_entries(session_id)
        prefs: dict[str, Any] = {}
        for entry in entries:
            if entry.category == MemoryCategory.PREFERENCE:
                prefs[entry.content] = entry.metadata
        return prefs

    # ─── Management ───────────────────────────────────────────

    def clear_session(self, session_id: str) -> int:
        """Limpia la memoria de una sesion."""
        with self._lock:
            ids = self._session_index.pop(session_id, [])
            for mid in ids:
                self._entries.pop(mid, None)
            self._stats.short_term_count = len(self._entries)
            self._stats.evictions += len(ids)
            return len(ids)

    def cleanup_expired(self) -> int:
        """Limpia entradas expiradas."""
        with self._lock:
            expired = [
                mid for mid, e in self._entries.items()
                if e.is_expired
            ]
            for mid in expired:
                entry = self._entries.pop(mid)
                # Limpiar indices
                sid = entry.session_id
                if sid in self._session_index:
                    self._session_index[sid] = [
                        i for i in self._session_index[sid] if i != mid
                    ]
                cat = entry.category
                if cat in self._category_index:
                    self._category_index[cat] = [
                        i for i in self._category_index[cat] if i != mid
                    ]

            self._stats.short_term_count = len(self._entries)
            self._stats.evictions += len(expired)
            return len(expired)

    @property
    def stats(self) -> MemoryStats:
        """Estadisticas de short-term memory."""
        self._stats.short_term_count = len(self._entries)
        return self._stats

    # ─── Privados ─────────────────────────────────────────────

    def _evict_low_importance(self) -> None:
        """Evicta entradas con menor importancia."""
        if not self._entries:
            return

        # Encontrar la entrada con menor importancia
        min_id = min(
            self._entries,
            key=lambda mid: self._entries[mid].importance,
        )
        entry = self._entries.pop(min_id)

        # Limpiar indices
        sid = entry.session_id
        if sid in self._session_index:
            self._session_index[sid] = [
                i for i in self._session_index[sid] if i != min_id
            ]

    @staticmethod
    def _score(entry: MemoryEntry, query: MemoryQuery) -> float:
        """Score de relevancia para short-term."""
        score = 0.0

        # Importance
        score += entry.importance * 0.4

        # Recency
        age = time.time() - entry.created_at
        recency = max(0.0, 1.0 - (age / 7200.0))  # Decae en 2h
        score += recency * 0.3

        # Keyword overlap
        if query.text:
            query_words = set(query.text.lower().split())
            entry_words = set(entry.content.lower().split())
            overlap = len(query_words & entry_words)
            total = max(len(query_words), 1)
            score += (overlap / total) * 0.3

        # Category match bonus
        if query.categories and entry.category in query.categories:
            score += 0.2

        return min(score, 1.0)
