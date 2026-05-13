"""
dna_loader_parts — modularized DNALoader.

Public API re-exported for backward compatibility.
"""

import threading
from typing import Optional

from ._imports import (
    LogicModule, DomainRule, ValidationGate, GlossaryEntry,
    DNA_ROOT, YAML_AVAILABLE,
)
from ._loader import DNALoader

__all__ = [
    "DNALoader",
    "LogicModule",
    "DomainRule",
    "ValidationGate",
    "GlossaryEntry",
    "DNA_ROOT",
    "YAML_AVAILABLE",
    "get_dna_loader",
]


# === Singleton ===
_dna_loader_instance: Optional[DNALoader] = None
_dna_loader_lock = threading.Lock()


def get_dna_loader() -> DNALoader:
    """Obtiene la instancia singleton del DNALoader."""
    global _dna_loader_instance
    if _dna_loader_instance is None:
        with _dna_loader_lock:
            if _dna_loader_instance is None:
                _dna_loader_instance = DNALoader()
    return _dna_loader_instance
