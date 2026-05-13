"""
Pipeline de entrada del Asistente.

Procesa el mensaje crudo del usuario en tres fases:
  1. Sanitize: Limpieza y validacion
  2. Parse: Extraccion de estructura y entidades
  3. Enrich: Enriquecimiento con contexto y memoria
"""

from .sanitizer import InputSanitizer
from .parser import InputParser
from .enricher import InputEnricher

__all__ = [
    "InputSanitizer",
    "InputParser",
    "InputEnricher",
]
