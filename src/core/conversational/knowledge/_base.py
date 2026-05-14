"""
Base de conocimiento del Asistente - KnowledgeBase

Almacena, indexa y recupera conocimiento estructurado.
Busqueda por keyword overlap, categorias y tags.
Thread-safe.
"""

import logging
import threading
import time
from typing import Any

from ...types.base import Result, Ok
from ._types import (
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeResult,
    KnowledgeType,
    _extract_keywords,
)

logger = logging.getLogger("zenic_agents.conversational.knowledge")


class KnowledgeBase:
    """
    Base de conocimiento del asistente.

    Almacena, indexa y recupera conocimiento estructurado.
    Busqueda por keyword overlap, categorias y tags.
    Thread-safe.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}
        self._keyword_index: dict[str, list[str]] = {}
        self._category_index: dict[str, list[str]] = {}
        self._tag_index: dict[str, list[str]] = {}
        self._type_index: dict[KnowledgeType, list[str]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._stats = {
            "total_stored": 0,
            "total_retrieved": 0,
            "total_entries": 0,
        }

    # ─── Store ─────────────────────────────────────────────────

    def store(self, entry: KnowledgeEntry) -> Result[str]:
        """Almacena una entrada y la indexa."""
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._evict_lowest_importance()

            self._entries[entry.entry_id] = entry

            # Indexar por keywords
            for kw in entry.keywords:
                kw_lower = kw.lower()
                if kw_lower not in self._keyword_index:
                    self._keyword_index[kw_lower] = []
                self._keyword_index[kw_lower].append(entry.entry_id)

            # Indexar por categoria
            cat = entry.category
            if cat not in self._category_index:
                self._category_index[cat] = []
            self._category_index[cat].append(entry.entry_id)

            # Indexar por tags
            for tag in entry.tags:
                tag_lower = tag.lower()
                if tag_lower not in self._tag_index:
                    self._tag_index[tag_lower] = []
                self._tag_index[tag_lower].append(entry.entry_id)

            # Indexar por tipo
            ktype = entry.knowledge_type
            if ktype not in self._type_index:
                self._type_index[ktype] = []
            self._type_index[ktype].append(entry.entry_id)

            self._stats["total_stored"] += 1
            self._stats["total_entries"] = len(self._entries)

            return Ok(entry.entry_id)

    def store_concept(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> Result[str]:
        """Almacena un concepto."""
        # Auto-extraer keywords del contenido si no se proveen
        if not keywords:
            keywords = _extract_keywords(title + " " + content)

        entry = KnowledgeEntry(
            title=title,
            content=content,
            knowledge_type=KnowledgeType.CONCEPT,
            category=category,
            tags=tags or [],
            keywords=keywords,
        )
        return self.store(entry)

    # ─── Retrieve ──────────────────────────────────────────────

    def retrieve(self, query: KnowledgeQuery) -> KnowledgeResult:
        """Busca en la base de conocimiento."""
        start = time.time()

        with self._lock:
            # Buscar por keywords del query
            query_keywords = _extract_keywords(query.text)
            candidate_ids: dict[str, float] = {}

            # Score por keyword overlap
            for kw in query_keywords:
                kw_lower = kw.lower()
                for index_kw, entry_ids in self._keyword_index.items():
                    if kw_lower in index_kw or index_kw in kw_lower:
                        score = 1.0 if kw_lower == index_kw else 0.5
                        for eid in entry_ids:
                            candidate_ids[eid] = candidate_ids.get(eid, 0.0) + score

            # Si no hay matches por keyword, buscar por categoria
            if not candidate_ids and query.categories:
                for cat in query.categories:
                    for eid in self._category_index.get(cat, []):
                        candidate_ids[eid] = candidate_ids.get(eid, 0.0) + 0.3

            # Filtrar y score
            candidates: list[KnowledgeEntry] = []
            for eid, score in candidate_ids.items():
                entry = self._entries.get(eid)
                if entry is None:
                    continue

                # Filtros
                if query.knowledge_types and entry.knowledge_type not in query.knowledge_types: continue
                if query.categories and entry.category not in query.categories: continue
                if query.tags and not any(t in entry.tags for t in query.tags): continue
                if query.language and entry.language and entry.language != query.language: continue
                if query.min_importance > 0 and entry.importance < query.min_importance: continue

                # Boost por importancia
                score += entry.importance * 0.3
                # Boost por accesos
                score += min(entry.access_count * 0.02, 0.2)

                entry.metadata["_search_score"] = score
                entry.touch()
                candidates.append(entry)

            # Si aun no hay candidatos, buscar por texto
            if not candidates:
                candidates = self._text_search(query)

        # Ordenar por score
        candidates.sort(
            key=lambda e: e.metadata.get("_search_score", 0.0),
            reverse=True,
        )
        results = candidates[:query.max_results]

        elapsed = (time.time() - start) * 1000
        self._stats["total_retrieved"] += 1

        return KnowledgeResult(
            entries=results,
            total_matches=len(candidates),
            search_time_ms=elapsed,
            query=query,
        )

    # ─── Query helpers ─────────────────────────────────────────

    def search(
        self,
        text: str,
        max_results: int = 5,
        category: str | None = None,
    ) -> KnowledgeResult:
        """Busqueda simplificada."""
        query = KnowledgeQuery(
            text=text,
            categories=[category] if category else [],
            max_results=max_results,
        )
        return self.retrieve(query)

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """Obtiene una entrada por ID."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.touch()
        return entry

    def get_related(self, entry_id: str, max_results: int = 5) -> list[KnowledgeEntry]:
        """Obtiene entradas relacionadas."""
        entry = self._entries.get(entry_id)
        if entry is None:
            return []

        related: list[KnowledgeEntry] = []
        for rid in entry.related_ids:
            r = self._entries.get(rid)
            if r:
                related.append(r)

        # Buscar por tags compartidos
        if len(related) < max_results:
            for tag in entry.tags:
                for eid in self._tag_index.get(tag.lower(), []):
                    if eid != entry_id and eid not in [e.entry_id for e in related]:
                        r = self._entries.get(eid)
                        if r:
                            related.append(r)
                    if len(related) >= max_results:
                        break
                if len(related) >= max_results:
                    break

        return related[:max_results]

    # ─── Stats ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas de la base de conocimiento."""
        with self._lock:
            return {
                **self._stats,
                "categories": list(self._category_index.keys()),
                "types": {t.value: len(ids) for t, ids in self._type_index.items()},
            }

    # ─── Privados ──────────────────────────────────────────────

    def _evict_lowest_importance(self) -> None:
        """Evicta la entrada con menor importancia."""
        if not self._entries:
            return
        min_id = min(self._entries, key=lambda eid: self._entries[eid].importance)
        self._remove_entry(min_id)

    def _remove_entry(self, entry_id: str) -> None:
        """Remueve una entrada y limpia indices."""
        entry = self._entries.pop(entry_id, None)
        if entry is None: return
        for kw in entry.keywords:
            if kw.lower() in self._keyword_index:
                self._keyword_index[kw.lower()] = [i for i in self._keyword_index[kw.lower()] if i != entry_id]
        if entry.category in self._category_index:
            self._category_index[entry.category] = [i for i in self._category_index[entry.category] if i != entry_id]
        for tag in entry.tags:
            if tag.lower() in self._tag_index:
                self._tag_index[tag.lower()] = [i for i in self._tag_index[tag.lower()] if i != entry_id]
        if entry.knowledge_type in self._type_index:
            self._type_index[entry.knowledge_type] = [i for i in self._type_index[entry.knowledge_type] if i != entry_id]

    def _text_search(self, query: KnowledgeQuery) -> list[KnowledgeEntry]:
        """Busqueda de texto cuando no hay keyword matches."""
        query_words = set(query.text.lower().split())
        candidates: list[tuple[KnowledgeEntry, float]] = []

        for entry in self._entries.values():
            entry_words = set(
                (entry.title + " " + entry.content).lower().split()[:100]
            )
            overlap = len(query_words & entry_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                candidates.append((entry, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in candidates[:query.max_results]]
