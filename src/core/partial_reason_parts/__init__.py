"""
Partial Reasoning Manager - Response Contract for OpenAI-compatible partial responses.

Construye respuestas de Razonamiento Parcial como especifica el documento.
Incluye resumption_token y state para resume_from_partial().
"""

from .manager import PartialReasoningManager

__all__ = ["PartialReasoningManager"]
