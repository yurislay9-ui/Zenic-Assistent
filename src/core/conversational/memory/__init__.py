"""
Sistema de memoria del Asistente.

Tres niveles de memoria con scoring, retencion y retrieval:
  - WorkingMemory: Contexto inmediato (ultimos N mensajes)
  - ShortTermMemory: Memoria de sesion (datos, preferencias)
  - LongTermMemory: Memoria persistente (entre sesiones)
  - MemoryManager: Orquestador unificado con retrieval avanzado

Cada nivel tiene su propia politica de retencion y eviction.
"""

from .working_memory import WorkingMemory
from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .memory_scorer import MemoryScorer
from .manager import MemoryManager

__all__ = [
    "WorkingMemory",
    "ShortTermMemory",
    "LongTermMemory",
    "MemoryScorer",
    "MemoryManager",
]
