"""
ZENIC-AGENTS - NicheLoader (YAML-Driven Niche Template Registry)

Cargador de plantillas YAML de nichos que permite al TemplateEngine
descubrir, cargar y resolver CompositionPlans desde definiciones
declarativas por dominio/nicho.
"""

from ._imports import NicheTemplate, NICHE_ROOT, YAML_AVAILABLE
from .loader import NicheLoader
from .singleton import get_niche_loader

__all__ = [
    "NicheTemplate",
    "NicheLoader",
    "get_niche_loader",
    "NICHE_ROOT",
    "YAML_AVAILABLE",
]
