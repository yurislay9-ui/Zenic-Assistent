"""Shared imports, constants, and NicheTemplate dataclass for niche_loader_parts."""

import os
import logging
import threading
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from src.core.template_engine import CompositionPlan, TemplateBlock

logger = logging.getLogger(__name__)

# === Niche Root ===
# Path: src/core/niche_loader_parts/_imports.py → up 3 dirs to src/ → templates/niches
_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NICHE_ROOT = os.path.join(_SRC_ROOT, "templates", "niches")


@dataclass
class NicheTemplate:
    """Definicion declarativa de un nicho de negocio."""
    name: str
    domain: str
    subdomain: str
    description: str
    scale: str  # small, medium, large, enterprise

    # Composition
    base_template: str = "apps/base"
    app_template: str = ""
    blocks: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Entities
    entities: List[Dict[str, Any]] = field(default_factory=list)

    # Workflow
    typical_paths: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)

    # Features
    core_features: List[str] = field(default_factory=list)
    advanced_features: List[str] = field(default_factory=list)
    optional_features: List[str] = field(default_factory=list)

    # Risk
    data_sensitivity: str = "medium"
    compliance: List[str] = field(default_factory=list)
    backup_frequency: str = "daily"
    access_control: str = "basic"
    audit_trail: bool = False

    # Metadata
    yaml_path: str = ""
    loaded_at: str = ""

    def to_composition_plan(self) -> CompositionPlan:
        """Convierte este NicheTemplate en un CompositionPlan usable por TemplateEngine."""
        return CompositionPlan(
            base_template=self.base_template,
            app_template=self.app_template,
            blocks=list(self.blocks),
            variables=dict(self.variables),
            entities=list(self.entities),
        )

    @property
    def keywords(self) -> Set[str]:
        """Extrae keywords del nombre, dominio y descripcion para busqueda."""
        words = set()
        for source in [self.name, self.domain, self.subdomain, self.description]:
            for word in source.lower().replace("_", " ").replace("-", " ").split():
                if len(word) > 2:
                    words.add(word)
        # Agregar features como keywords
        for feat in self.core_features + self.advanced_features:
            for word in feat.lower().split():
                if len(word) > 3:
                    words.add(word)
        return words

    @property
    def entity_count(self) -> int:
        """Numero de entidades en este nicho."""
        return len(self.entities)

    @property
    def total_fields(self) -> int:
        """Total de campos en todas las entidades."""
        return sum(len(e.get("fields", [])) for e in self.entities)
