"""Mixin: Statistics and filtering methods for NicheLoader."""

from typing import Dict, Any, List

from ._imports import YAML_AVAILABLE


class StatsMixin:
    """Mixin providing statistics and compliance filtering."""

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del cargador de nichos."""
        if not self._loaded:
            self.load_all()

        total_entities = sum(n.entity_count for n in self._niches.values())
        total_fields = sum(n.total_fields for n in self._niches.values())

        sensitivity_dist = {}
        for n in self._niches.values():
            sensitivity_dist[n.data_sensitivity] = sensitivity_dist.get(n.data_sensitivity, 0) + 1

        scale_dist = {}
        for n in self._niches.values():
            scale_dist[n.scale] = scale_dist.get(n.scale, 0) + 1

        return {
            "total_niches": len(self._niches),
            "total_domains": len(self._domain_index),
            "total_entities": total_entities,
            "total_fields": total_fields,
            "sensitivity_distribution": sensitivity_dist,
            "scale_distribution": scale_dist,
            "yaml_available": YAML_AVAILABLE,
            "loaded": self._loaded,
        }

    def filter_by_compliance(self, regulation: str):
        """Filtra nichos que requieren una regulacion especifica."""
        if not self._loaded:
            self.load_all()
        reg_lower = regulation.lower()
        return [
            n for n in self._niches.values()
            if any(reg_lower in c.lower() for c in n.compliance)
        ]

    def filter_by_sensitivity(self, level: str):
        """Filtra nichos por nivel de sensibilidad de datos."""
        if not self._loaded:
            self.load_all()
        return [n for n in self._niches.values() if n.data_sensitivity == level]

    def filter_by_scale(self, scale: str):
        """Filtra nichos por escala."""
        if not self._loaded:
            self.load_all()
        return [n for n in self._niches.values() if n.scale == scale]

    def get_common_blocks(self) -> Dict[str, int]:
        """Retorna bloques usados y su frecuencia entre todos los nichos."""
        if not self._loaded:
            self.load_all()
        block_freq = {}
        for niche in self._niches.values():
            for block in niche.blocks:
                block_freq[block] = block_freq.get(block, 0) + 1
        return dict(sorted(block_freq.items(), key=lambda x: x[1], reverse=True))

    def get_common_entities(self) -> Dict[str, int]:
        """Retorna nombres de entidades y su frecuencia entre nichos."""
        if not self._loaded:
            self.load_all()
        entity_freq = {}
        for niche in self._niches.values():
            for entity in niche.entities:
                name = entity.get("name", "")
                if name:
                    entity_freq[name] = entity_freq.get(name, 0) + 1
        return dict(sorted(entity_freq.items(), key=lambda x: x[1], reverse=True))

    def get_domain_overview(self) -> Dict[str, Dict[str, Any]]:
        """Retorna overview de cada dominio con estadisticas."""
        if not self._loaded:
            self.load_all()
        overview = {}
        for domain, names in self._domain_index.items():
            niches = [self._niches[n] for n in names if n in self._niches]
            overview[domain] = {
                "niche_count": len(niches),
                "total_entities": sum(n.entity_count for n in niches),
                "total_fields": sum(n.total_fields for n in niches),
                "scales": list(set(n.scale for n in niches)),
                "compliance": list(set(c for n in niches for c in n.compliance)),
                "niche_names": sorted(names),
            }
        return overview
