"""
Routing del Asistente.

Selecciona el pipeline de procesamiento adecuado
basado en la intencion detectada, capacidades del
sistema y contexto de la sesion.
"""

from .router import AssistantRouter
from .pipeline_selector import PipelineSelector
from .fallback_chain import FallbackChain

__all__ = [
    "AssistantRouter",
    "PipelineSelector",
    "FallbackChain",
]
