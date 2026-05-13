"""
Base de conocimiento del Asistente - Tipos y Contratos de Datos

KnowledgeType enum, KnowledgeEntry, KnowledgeQuery, KnowledgeResult dataclasses.
"""

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ...types.base import new_id


class KnowledgeType(str, Enum):
    """Tipos de entrada en la base de conocimiento."""
    CONCEPT = "concept"           # Definicion o concepto
    PATTERN = "pattern"           # Patron de codigo o diseno
    TUTORIAL = "tutorial"         # Tutorial paso a paso
    REFERENCE = "reference"       # Referencia tecnica
    FAQ = "faq"                   # Pregunta frecuente
    BEST_PRACTICE = "best_practice"  # Mejor practica
    TROUBLESHOOT = "troubleshoot"    # Solucion de problemas


@dataclass
class KnowledgeEntry:
    """Entrada en la base de conocimiento."""
    entry_id: str = field(default_factory=lambda: new_id("kno"))
    title: str = ""
    content: str = ""
    knowledge_type: KnowledgeType = KnowledgeType.CONCEPT
    category: str = "general"       # programming, architecture, devops, etc.
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)
    source: str = "builtin"         # builtin, user, web, system
    language: str = ""              # Lenguaje de programacion (si aplica)
    importance: float = 0.5
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_code_related(self) -> bool:
        return self.knowledge_type in (
            KnowledgeType.PATTERN, KnowledgeType.REFERENCE,
            KnowledgeType.BEST_PRACTICE,
        )

    def touch(self) -> None:
        self.access_count += 1
        self.updated_at = time.time()

    def to_context_dict(self) -> dict[str, Any]:
        """Convierte a dict para inyeccion de contexto."""
        return {
            "title": self.title,
            "type": self.knowledge_type.value,
            "category": self.category,
            "content": self.content[:500],
            "tags": self.tags,
            "importance": self.importance,
        }


@dataclass
class KnowledgeQuery:
    """Query para buscar en la base de conocimiento."""
    text: str = ""
    knowledge_types: list[KnowledgeType] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    language: str = ""
    max_results: int = 10
    min_importance: float = 0.0


@dataclass
class KnowledgeResult:
    """Resultado de busqueda en la base de conocimiento."""
    entries: list[KnowledgeEntry] = field(default_factory=list)
    total_matches: int = 0
    search_time_ms: float = 0.0
    query: KnowledgeQuery = field(default_factory=KnowledgeQuery)

    @property
    def has_results(self) -> bool:
        return len(self.entries) > 0

    def to_context_string(self, max_entries: int = 5) -> str:
        """Convierte a string para inyectar en prompt."""
        if not self.entries:
            return ""
        lines: list[str] = []
        for entry in self.entries[:max_entries]:
            lines.append(
                f"[{entry.knowledge_type.value}/{entry.category}] "
                f"{entry.title}: {entry.content[:200]}"
            )
        return "\n".join(lines)


# ─── Keyword extraction helper ────────────────────────────────

_STOP_WORDS = {
    "el", "la", "los", "las", "de", "en", "es", "un", "una",
    "y", "o", "a", "por", "para", "con", "que", "se", "su",
    "the", "is", "are", "was", "a", "an", "and", "or", "but",
    "in", "on", "at", "to", "for", "of", "with", "it",
}


def _extract_keywords(text: str) -> list[str]:
    """Extrae keywords significativas de un texto."""
    words = re.findall(r"\b\w{3,}\b", text.lower())
    return [w for w in words if w not in _STOP_WORDS][:20]
