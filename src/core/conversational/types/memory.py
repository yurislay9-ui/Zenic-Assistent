"""
Tipos de memoria del Asistente.

Modela los tres niveles de memoria: working (inmediato),
short-term (sesion) y long-term (persistente), con
scoring de relevancia y politicas de retencion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import MemoryId, new_id


# ─── Niveles de memoria ──────────────────────────────────────

class MemoryType(str, Enum):
    """Tipo de almacenamiento de memoria."""
    WORKING = "working"        # En contexto inmediato (ultimos N mensajes)
    SHORT_TERM = "short_term"  # En la sesion actual
    LONG_TERM = "long_term"    # Persistente entre sesiones


class MemoryCategory(str, Enum):
    """Categoria del contenido almacenado."""
    FACT = "fact"              # Hecho o dato
    PREFERENCE = "preference"  # Preferencia del usuario
    CONTEXT = "context"        # Contexto de conversacion
    SKILL = "skill"            # Habilidad o patron aprendido
    CORRECTION = "correction"  # Correccion del usuario
    TOPIC = "topic"            # Tema de conversacion
    EMOTION = "emotion"        # Estado emocional detectado


# ─── Entrada de memoria ──────────────────────────────────────

@dataclass
class MemoryEntry:
    """
    Entrada individual de memoria.

    Cada entrada tiene scoring de relevancia, categoria,
    TTL y metadata para retrieval eficiente.
    """
    memory_id: MemoryId = field(default_factory=lambda: new_id("mem"))
    content: str = ""
    category: MemoryCategory = MemoryCategory.FACT
    memory_type: MemoryType = MemoryType.SHORT_TERM
    session_id: str = ""
    importance: float = 0.5       # 0.0 - 1.0, umbral para LTM
    relevance_score: float = 0.0  # Score calculado al recuperar
    access_count: int = 0         # Veces accedida
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    expires_at: float = 0.0       # 0 = sin expiracion
    tags: list[str] = field(default_factory=list)
    source: str = "user"          # user, assistant, system, tool
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Verifica si la entrada ha expirado."""
        if self.expires_at == 0.0:
            return False
        return time.time() > self.expires_at

    @property
    def is_important(self) -> bool:
        """True si la importancia supera el umbral para LTM."""
        return self.importance >= 0.7

    @property
    def age_seconds(self) -> float:
        """Segundos desde la creacion."""
        return time.time() - self.created_at

    def touch(self) -> None:
        """Actualiza el timestamp de ultimo acceso."""
        self.last_accessed = time.time()
        self.access_count += 1

    def decay_importance(self, factor: float = 0.95) -> None:
        """Decae la importancia con el tiempo."""
        self.importance *= factor

    def to_retrieval_dict(self) -> dict[str, Any]:
        """Convierte a diccionario para contexto de retrieval."""
        return {
            "content": self.content,
            "category": self.category.value,
            "importance": round(self.importance, 3),
            "source": self.source,
            "tags": self.tags,
        }


# ─── Query de memoria ────────────────────────────────────────

@dataclass
class MemoryQuery:
    """Query para buscar en la memoria."""
    text: str = ""
    categories: list[MemoryCategory] = field(default_factory=list)
    memory_types: list[MemoryType] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    min_importance: float = 0.0
    max_results: int = 10
    time_range: tuple[float, float] | None = None  # (from, to)

    def matches(self, entry: MemoryEntry) -> bool:
        """Verifica si una entrada matches esta query."""
        if entry.is_expired:
            return False
        if self.categories and entry.category not in self.categories:
            return False
        if self.memory_types and entry.memory_type not in self.memory_types:
            return False
        if self.min_importance > 0 and entry.importance < self.min_importance:
            return False
        if self.session_id and entry.session_id != self.session_id:
            return False
        if self.time_range:
            if not (self.time_range[0] <= entry.created_at <= self.time_range[1]):
                return False
        if self.tags and not any(t in entry.tags for t in self.tags):
            return False
        return True


# ─── Resultado de memoria ────────────────────────────────────

@dataclass
class MemoryResult:
    """Resultado de una busqueda en memoria."""
    entries: list[MemoryEntry] = field(default_factory=list)
    total_matches: int = 0
    query: MemoryQuery = field(default_factory=MemoryQuery)
    search_time_ms: float = 0.0

    @property
    def has_results(self) -> bool:
        return len(self.entries) > 0

    @property
    def top_entry(self) -> MemoryEntry | None:
        """Entrada con mayor relevancia."""
        if not self.entries:
            return None
        return max(self.entries, key=lambda e: e.relevance_score)

    def to_context_string(self, max_entries: int = 5) -> str:
        """Convierte las entradas a string para inyectar en contexto."""
        if not self.entries:
            return ""
        lines: list[str] = []
        for entry in self.entries[:max_entries]:
            lines.append(
                f"[{entry.category.value}] {entry.content} "
                f"(relevance={entry.relevance_score:.2f})"
            )
        return "\n".join(lines)


# ─── Estadisticas de memoria ─────────────────────────────────

@dataclass
class MemoryStats:
    """Estadisticas del sistema de memoria."""
    working_count: int = 0
    short_term_count: int = 0
    long_term_count: int = 0
    total_stored: int = 0
    total_retrieved: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    evictions: int = 0
    avg_retrieval_ms: float = 0.0

    @property
    def total_active(self) -> int:
        return self.working_count + self.short_term_count + self.long_term_count

    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0
