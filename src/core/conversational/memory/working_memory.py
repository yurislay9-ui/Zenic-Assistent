"""
Working Memory del Asistente.

Memoria de contexto inmediato: los ultimos N mensajes
y datos relevantes para la conversacion actual.

Caracteristicas:
  - Tamano fijo (sliding window)
  - Acceso O(1) por posicion
  - Auto-eviction por LRU
  - Thread-safe
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ...types.base import Result, Ok, Err
from ...types.memory import (
    MemoryEntry, MemoryQuery, MemoryResult,
    MemoryType, MemoryCategory, MemoryStats,
)
from ...config.constants import MEMORY_MAX_WORKING


@dataclass
class WorkingMemoryConfig:
    """Configuracion de working memory."""
    max_entries: int = MEMORY_MAX_WORKING
    ttl_seconds: float = 0.0       # 0 = sin expiracion


class WorkingMemory:
    """
    Working Memory: contexto inmediato.

    Almacena los ultimos N entries relevantes para
    la conversacion actual. Sliding window con LRU eviction.
    """

    def __init__(self, config: WorkingMemoryConfig | None = None) -> None:
        self._config = config or WorkingMemoryConfig()
        self._entries: list[MemoryEntry] = []
        self._lock = threading.Lock()
        self._stats = MemoryStats()

    # ─── Store ────────────────────────────────────────────────

    def store(self, entry: MemoryEntry) -> Result[bool]:
        """
        Almacena una entrada en working memory.

        Si excede el limite, evicta la entrada mas antigua.
        """
        with self._lock:
            # Marcar como working memory
            entry.memory_type = MemoryType.WORKING

            # Eviction si es necesario
            while len(self._entries) >= self._config.max_entries:
                self._evict_oldest()

            self._entries.append(entry)
            self._stats.working_count = len(self._entries)
            self._stats.total_stored += 1

            return Ok(True)

    # ─── Retrieve ─────────────────────────────────────────────

    def retrieve(self, query: MemoryQuery) -> MemoryResult:
        """
        Busca entradas que matcheen la query.

        Scoring: recency + importance + keyword overlap.
        """
        start = time.time()

        with self._lock:
            # Filtrar por query
            candidates = [
                e for e in self._entries
                if not e.is_expired and query.matches(e)
            ]

            # Scoring
            for entry in candidates:
                entry.relevance_score = self._score_entry(entry, query)
                entry.touch()

            # Ordenar por relevancia
            candidates.sort(key=lambda e: e.relevance_score, reverse=True)

            # Limitar resultados
            results = candidates[:query.max_results]

        elapsed = (time.time() - start) * 1000
        self._stats.total_retrieved += 1
        self._stats.cache_hits += len(results)
        self._stats.cache_misses += max(0, len(candidates) - len(results))
        self._stats.avg_retrieval_ms = (
            (self._stats.avg_retrieval_ms + elapsed) / 2
        )

        return MemoryResult(
            entries=results,
            total_matches=len(candidates),
            query=query,
            search_time_ms=elapsed,
        )

    def get_recent(self, count: int = 10) -> list[MemoryEntry]:
        """Obtiene las ultimas N entradas."""
        with self._lock:
            return self._entries[-count:]

    def get_context_string(self, max_entries: int = 5) -> str:
        """Obtiene contexto como string para inyectar en prompt."""
        with self._lock:
            if not self._entries:
                return ""
            recent = self._entries[-max_entries:]
            lines: list[str] = []
            for entry in recent:
                lines.append(
                    f"[{entry.category.value}] {entry.content}"
                )
            return "\n".join(lines)

    # ─── Management ───────────────────────────────────────────

    def clear(self) -> int:
        """Limpia toda la working memory. Retorna entradas eliminadas."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._stats.working_count = 0
            self._stats.evictions += count
            return count

    @property
    def size(self) -> int:
        """Cantidad de entradas activas."""
        return len(self._entries)

    @property
    def stats(self) -> MemoryStats:
        """Estadisticas de working memory."""
        self._stats.working_count = len(self._entries)
        return self._stats

    # ─── Privados ─────────────────────────────────────────────

    def _evict_oldest(self) -> None:
        """Evicta la entrada mas antigua (debe llamarse con lock)."""
        if self._entries:
            self._entries.pop(0)
            self._stats.evictions += 1

    @staticmethod
    def _score_entry(entry: MemoryEntry, query: MemoryQuery) -> float:
        """Calcula score de relevancia de una entrada."""
        score = 0.0

        # Recency: mas reciente = mas relevante
        age = time.time() - entry.created_at
        recency = max(0.0, 1.0 - (age / 3600.0))  # Decae en 1h
        score += recency * 0.3

        # Importance: entrada con mas importancia
        score += entry.importance * 0.3

        # Keyword overlap
        if query.text:
            query_words = set(query.text.lower().split())
            entry_words = set(entry.content.lower().split())
            overlap = len(query_words & entry_words)
            total = len(query_words)
            if total > 0:
                score += (overlap / total) * 0.4

        # Boost por access count
        if entry.access_count > 0:
            score += min(entry.access_count * 0.05, 0.2)

        return min(score, 1.0)
