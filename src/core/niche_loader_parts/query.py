"""Mixin: Query methods for NicheLoader."""

from typing import Optional, List, Dict, Any

from ._imports import CompositionPlan


class QueryMixin:
    """Mixin providing niche query and search methods."""

    def get(self, name: str):
        """Obtiene un nicho por nombre exacto."""
        if not self._loaded:
            self.load_all()
        return self._niches.get(name)

    def get_plan(self, name: str) -> Optional[CompositionPlan]:
        """Obtiene un CompositionPlan para un nicho por nombre."""
        niche = self.get(name)
        if niche:
            return niche.to_composition_plan()
        return None

    def list_domains(self) -> List[str]:
        """Lista todos los dominios disponibles."""
        if not self._loaded:
            self.load_all()
        return sorted(self._domain_index.keys())

    def list_niches(self, domain: str = "") -> List[str]:
        """Lista nichos, opcionalmente filtrados por dominio."""
        if not self._loaded:
            self.load_all()
        if domain:
            return sorted(self._domain_index.get(domain, []))
        return sorted(self._niches.keys())

    def get_by_domain(self, domain: str):
        """Obtiene todos los nichos de un dominio."""
        if not self._loaded:
            self.load_all()
        names = self._domain_index.get(domain, [])
        return [self._niches[n] for n in names if n in self._niches]

    def search(self, query: str, limit: int = 10):
        """
        Busca nichos relevantes basado en una consulta.

        Usa keyword matching contra nombre, dominio, descripcion y features.
        Retorna nichos ordenados por relevancia.
        """
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        query_words = set(query_lower.replace("_", " ").replace("-", " ").split())

        scored = []
        for niche in self._niches.values():
            score = 0

            # Exact name match (highest priority)
            if query_lower == niche.name.lower():
                score += 100
            elif query_lower in niche.name.lower():
                score += 50

            # Domain match
            if query_lower == niche.domain.lower():
                score += 40
            elif query_lower in niche.domain.lower():
                score += 20

            # Subdomain match
            if query_lower in niche.subdomain.lower():
                score += 15

            # Keyword overlap
            niche_kw = niche.keywords
            overlap = query_words & niche_kw
            score += len(overlap) * 10

            # Description match
            desc_words = set(niche.description.lower().split())
            desc_overlap = query_words & desc_words
            score += len(desc_overlap) * 5

            # Compliance match
            for comp in niche.compliance:
                if comp.lower() in query_lower:
                    score += 15

            # Scale match
            if any(w in query_lower for w in ["enterprise", "erp", "large"]):
                if niche.scale in ("enterprise", "large"):
                    score += 10

            if score > 0:
                scored.append((score, niche))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:limit]]

    def suggest_for_description(self, description: str) -> List[Dict[str, Any]]:
        """
        Sugiere nichos relevantes basado en una descripcion de proyecto.

        Returns:
            Lista de dicts con name, domain, description, relevance_score
        """
        results = self.search(description, limit=20)
        suggestions = []
        for niche in results:
            # Calculate relevance based on keyword overlap
            query_words = set(description.lower().replace("_", " ").split())
            niche_kw = niche.keywords
            overlap = query_words & niche_kw
            relevance = min(100, len(overlap) * 15)

            suggestions.append({
                "name": niche.name,
                "domain": niche.domain,
                "description": niche.description,
                "scale": niche.scale,
                "relevance_score": relevance,
                "entity_count": niche.entity_count,
                "blocks": niche.blocks,
                "compliance": niche.compliance,
            })
        return suggestions
