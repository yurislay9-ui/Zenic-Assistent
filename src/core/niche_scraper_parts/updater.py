"""
NicheAutoUpdater: Auto-updates niche YAMLs from trending patterns.
"""

import time
import logging
from typing import Dict, Any, List, Optional

from ._imports import EvolutionEntry, logger
from . import _imports as _niche_imports
from .trending import TrendingAnalyzer


class NicheAutoUpdater:
    """
    Actualizador automático de nichos YAML.

    Conecta el TrendingAnalyzer con el NicheLoader para:
    1. Detectar patrones emergentes de GitHub
    2. Comparar con los nichos existentes
    3. Fusionar nuevos bloques/entidades si son relevantes
    4. Guardar los YAML actualizados
    """

    def __init__(self, niche_loader=None, scrap_agent=None):
        self._loader = niche_loader
        self._analyzer = TrendingAnalyzer(scrap_agent)
        self._niche_root = ""
        self._mutations_count = 0
        self._last_scan = 0.0
        self._copied_niches = set()
        self._copied_entities = set()

        if niche_loader:
            self._niche_root = niche_loader._root

    async def auto_update(self, language: str = "python") -> Dict[str, Any]:
        """
        Ejecuta un ciclo completo de auto-actualización.

        1. Analiza trending repos
        2. Para cada patrón detectado, busca nichos relevantes
        3. Fusiona nuevos bloques/entidades
        4. Guarda cambios en YAML

        Returns:
            Dict con estadísticas de la actualización
        """
        if not self._loader or not _niche_imports.YAML_AVAILABLE:
            return {"error": "NicheLoader or PyYAML not available"}

        self._last_scan = time.time()
        mutations = []

        # Step 1: Analyze trending
        trending_results = await self._analyzer.analyze_trending(language)

        # Step 2: For each trending result, find matching niches
        for result in trending_results:
            patterns = result.get("patterns_detected", {})
            suggested_blocks = patterns.get("suggested_blocks", [])
            suggested_entities = patterns.get("suggested_entities", [])

            if not suggested_blocks and not suggested_entities:
                continue

            # Search for niches that match the topic
            topic = result.get("topic", "")
            matching_niches = self._loader.search(topic, limit=5)

            for niche in matching_niches:
                # Step 3: Merge new blocks
                # Use a copy of the blocks list to avoid mutating shared objects
                if niche.name not in self._copied_niches:
                    niche.blocks = niche.blocks.copy()
                    self._copied_niches.add(niche.name)
                for block in suggested_blocks:
                    if block not in niche.blocks:
                        niche.blocks.append(block)
                        entry = EvolutionEntry(
                            niche_name=niche.name,
                            mutation_type="block_added",
                            description=f"Bloque '{block}' añadido por detección de librería trending",
                            source_repo=f"github:trending:{topic}",
                            old_value="",
                            new_value=block,
                        )
                        self._analyzer._evolution_log.append(entry)
                        mutations.append(entry)

                # Step 4: Merge new entities
                # Use a copy of the entities list to avoid mutating shared objects
                if niche.name not in self._copied_entities:
                    niche.entities = niche.entities.copy()
                    self._copied_entities.add(niche.name)
                for entity in suggested_entities:
                    entity_name = entity.get("name", "")
                    existing_names = [e.get("name", "") for e in niche.entities]
                    if entity_name not in existing_names:
                        niche.entities.append(entity)
                        entry = EvolutionEntry(
                            niche_name=niche.name,
                            mutation_type="entity_added",
                            description=f"Entidad '{entity_name}' añadida por patrón trending",
                            source_repo=f"github:trending:{topic}",
                            old_value="",
                            new_value=entity_name,
                        )
                        self._analyzer._evolution_log.append(entry)
                        mutations.append(entry)

                # Step 5: Save updated YAML
                if mutations:
                    self._save_niche_yaml(niche)

        self._mutations_count += len(mutations)

        return {
            "mutations_applied": len(mutations),
            "total_mutations": self._mutations_count,
            "trending_analyzed": len(trending_results),
            "last_scan": self._last_scan,
            "mutations_detail": [
                {
                    "niche": m.niche_name,
                    "type": m.mutation_type,
                    "new_value": m.new_value,
                    "source": m.source_repo,
                }
                for m in mutations[:20]  # Limit detail to 20
            ],
        }

    def _save_niche_yaml(self, niche) -> bool:
        """Guarda un nicho actualizado de vuelta a su archivo YAML."""
        if not _niche_imports.YAML_AVAILABLE or not niche.yaml_path:
            return False

        try:
            import yaml
        except ImportError:
            logger.error("NicheAutoUpdater: PyYAML not available — cannot save niche YAML")
            return False

        try:
            data = {
                "niche": {
                    "name": niche.name,
                    "domain": niche.domain,
                    "subdomain": niche.subdomain,
                    "description": niche.description,
                    "scale": niche.scale,
                },
                "composition": {
                    "base_template": niche.base_template,
                    "app_template": niche.app_template,
                    "blocks": niche.blocks,
                    "variables": niche.variables,
                },
                "entities": niche.entities,
                "workflow": {
                    "typical_paths": niche.typical_paths,
                    "triggers": niche.triggers,
                },
                "features": {
                    "core": niche.core_features,
                    "advanced": niche.advanced_features,
                    "optional": niche.optional_features,
                },
                "risk_assessment": {
                    "data_sensitivity": niche.data_sensitivity,
                    "compliance": niche.compliance,
                    "backup_frequency": niche.backup_frequency,
                    "access_control": niche.access_control,
                    "audit_trail": niche.audit_trail,
                },
            }

            with open(niche.yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            logger.info(f"NicheAutoUpdater: Saved updated niche '{niche.name}'")
            return True

        except Exception as e:
            logger.error(f"NicheAutoUpdater: Error saving niche '{niche.name}': {e}")
            return False

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del auto-updater."""
        return {
            "total_mutations": self._mutations_count,
            "last_scan": self._last_scan,
            "evolution_entries": len(self._analyzer._evolution_log),
            "yaml_available": _niche_imports.YAML_AVAILABLE,
        }
