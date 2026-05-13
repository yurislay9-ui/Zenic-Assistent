"""
Base de conocimiento del Asistente.

Almacena y recupera conocimiento estructurado para
enriquecer las respuestas del asistente.
"""

from ._types import (
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeResult,
    KnowledgeType,
)
from ._base import KnowledgeBase

__all__ = [
    "KnowledgeBase",
    "KnowledgeEntry",
    "KnowledgeType",
    "KnowledgeQuery",
    "KnowledgeResult",
]
