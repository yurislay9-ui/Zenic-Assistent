"""
DNALoader — main class inheriting from mixins.
"""

import logging
from typing import Dict, Any, Optional

from ._imports import logger, DNA_ROOT, YAML_AVAILABLE
from ._loaders_mixin import LoadersMixin
from ._logic_modules_mixin import LogicModulesMixin
from ._domain_validation_mixin import DomainValidationMixin
from ._glossary_mixin import GlossaryMixin


class DNALoader(GlossaryMixin, DomainValidationMixin, LogicModulesMixin, LoadersMixin):
    """
    Cargador de las 4 Plantillas Maestras de ADN Técnico.

    Carga, indexa y provee acceso a:
    - 68 módulos de lógica atómica
    - 20 industrias con reglas de negocio
    - 121 gates de validación de calidad
    - 133 transformaciones de glosario profesional
    """

    def __init__(self, dna_root: str = ""):
        self._root = dna_root or DNA_ROOT
        self._logic_modules: Dict[str, "LogicModule"] = {}
        self._domain_rules: Dict[str, "DomainRule"] = {}
        self._validation_gates: list = []
        self._domain_gates: Dict[str, list] = {}
        self._glossary: list = []
        self._error_messages: Dict[str, str] = {}
        self._feature_descriptions: Dict[str, Dict] = {}
        self._communication_templates: list = []
        self._loaded = False

        # Indexes for fast lookup
        self._modules_by_domain: Dict[str, list] = {}
        self._gates_by_category: Dict[str, list] = {}

    def load_all(self) -> Dict[str, int]:
        """Carga las 4 plantillas maestras. Returns counts."""
        counts = {}

        # 1. Logic Modules
        counts["logic_modules"] = self._load_logic_modules()

        # 2. Domain Expert Rules
        counts["domain_rules"] = self._load_domain_rules()

        # 3. Validation Gates
        counts["validation_gates"] = self._load_validation_gates()

        # 4. Professional Glossary
        counts["glossary_entries"] = self._load_glossary()

        self._loaded = True
        logger.info(f"DNALoader: Loaded {counts}")
        return counts

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del cargador de ADN."""
        if not self._loaded:
            self.load_all()
        return {
            "logic_modules": len(self._logic_modules),
            "domain_rules": len(self._domain_rules),
            "validation_gates": len(self._validation_gates),
            "glossary_entries": len(self._glossary),
            "error_messages": len(self._error_messages),
            "feature_descriptions": len(self._feature_descriptions),
            "communication_templates": len(self._communication_templates),
            "domains_with_modules": list(self._modules_by_domain.keys()),
            "yaml_available": YAML_AVAILABLE,
        }

    def list_all_modules(self):
        """Public accessor for all loaded logic modules."""
        return list(getattr(self, '_logic_modules', {}).values())

    def list_all_domain_rules(self):
        """Public accessor for all domain rules."""
        return list(getattr(self, '_domain_rules', {}).values())
