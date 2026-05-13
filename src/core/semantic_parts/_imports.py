"""
Shared imports, constants, and data classes for semantic_parts.

FIX (Phase 4): Removed unused top-level imports (os, re, json, Optional,
Tuple) that are never consumed by child modules via `from ._imports import`.
Only imports actually used within this file or consumed by children are kept.
"""

import time
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field

# Lazy numpy import — avoids loading ~50-100MB into RAM on module import
# Call _get_numpy() when needed instead of using np directly.
# Check HAS_NUMPY before using numpy-dependent features.
HAS_NUMPY: bool = False  # Updated to True on successful lazy import
_np = None
_numpy_loading = False  # Guard against concurrent loading

def _get_numpy():
    """Lazy-load numpy only when actually needed (saves ~50-100MB RAM on Xiaomi).

    Thread-safe: uses _numpy_loading flag to prevent concurrent imports.
    Returns numpy module on success, None on failure.
    Check HAS_NUMPY after calling to determine availability.
    """
    global _np, HAS_NUMPY, _numpy_loading
    if _np is not None and _np is not False:
        return _np
    if _numpy_loading:
        # Another thread is loading numpy; wait and re-check
        import time
        for _ in range(50):  # Wait up to 5s
            time.sleep(0.1)
            if _np is not None and _np is not False:
                return _np
            if not _numpy_loading:
                break
        return None
    _numpy_loading = True
    try:
        import numpy as _np_mod
        _np = _np_mod
        HAS_NUMPY = True
    except ImportError:
        _np = False  # Sentinel: tried and failed
        HAS_NUMPY = False
    finally:
        _numpy_loading = False
    return _np if _np is not False else None


def _ensure_numpy():
    """Convenience: call _get_numpy() and return it, or raise ImportError."""
    np = _get_numpy()
    if np is None:
        raise ImportError("numpy is not available — embeddings pipeline disabled")
    return np

logger = logging.getLogger(__name__)

# === Model Configuration ===
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

# Intent prototype embeddings (pre-computed on first use)
INTENT_PROTOTYPES = {
    "CREATE": [
        "create a new module",
        "implement a feature",
        "add new functionality",
        "generate code for",
        "crear un nuevo modulo",
        "implementar una funcionalidad",
        "agregar nueva caracteristica",
        "generar codigo para",
        "nuevo archivo",
    ],
    "REFACTOR": [
        "refactor the code",
        "restructure the module",
        "reorganize the project",
        "clean up the code",
        "refactorizar el codigo",
        "reestructurar el modulo",
        "reorganizar el proyecto",
        "limpiar el codigo",
    ],
    "DELETE": [
        "delete the file",
        "remove the function",
        "eliminate the code",
        "eliminar el archivo",
        "borrar la funcion",
        "quitar el codigo",
    ],
    "SEARCH": [
        "search for the definition",
        "find where the function is",
        "locate the class",
        "buscar donde se define",
        "encontrar la funcion",
        "localizar la clase",
        "donde esta definido",
    ],
    "ANALYZE": [
        "analyze the code structure",
        "review the implementation",
        "check the quality",
        "analizar la estructura",
        "revisar la implementacion",
        "verificar la calidad",
    ],
    "EXPLAIN": [
        "explain how this works",
        "describe the function",
        "what does this code do",
        "explicar como funciona",
        "describir la funcion",
        "que hace este codigo",
    ],
    "DEBUG": [
        "debug the error",
        "fix the bug",
        "correct the issue",
        "depurar el error",
        "corregir el bug",
        "arreglar el problema",
        "solucionar el fallo",
    ],
    "OPTIMIZE": [
        "optimize the performance",
        "improve the speed",
        "make it faster",
        "optimizar el rendimiento",
        "mejorar la velocidad",
        "hacerlo mas rapido",
    ],
}

GOAL_PROTOTYPES = {
    "BUG_FIX": [
        "fix the bug",
        "correct the error",
        "resolve the issue",
        "corregir el error",
        "arreglar el bug",
        "solucionar el problema",
    ],
    "FEATURE_ADD": [
        "add new feature",
        "implement new functionality",
        "create new capability",
        "agregar nueva funcionalidad",
        "implementar nueva caracteristica",
    ],
    "SECURITY_HARDEN": [
        "improve security",
        "fix vulnerability",
        "harden authentication",
        "mejorar seguridad",
        "corregir vulnerabilidad",
        "fortalecer autenticacion",
    ],
    "PERFORMANCE": [
        "optimize speed",
        "reduce latency",
        "improve performance",
        "optimizar velocidad",
        "reducir latencia",
        "mejorar rendimiento",
    ],
    "MODERN_PATTERN": [
        "update to modern pattern",
        "migrate to new approach",
        "upgrade architecture",
        "actualizar patron moderno",
        "migrar a nuevo enfoque",
        "actualizar arquitectura",
    ],
    "COMPLEXITY_REDUCTION": [
        "simplify the code",
        "reduce complexity",
        "make it simpler",
        "simplificar el codigo",
        "reducir complejidad",
        "hacerlo mas simple",
    ],
    "READABILITY": [
        "improve readability",
        "add comments",
        "make code clearer",
        "mejorar legibilidad",
        "agregar comentarios",
        "hacer codigo mas claro",
    ],
}


@dataclass
class SemanticResult:
    """Resultado de clasificación semántica."""
    operation: str = "SEARCH"
    goal: str = "FEATURE_ADD"
    confidence: float = 0.0           # 0.0-1.0, similitud coseno del mejor prototype
    source: str = "embedding"          # "embedding" or "fallback"
    similarities: Dict[str, float] = field(default_factory=dict)  # top similarities per intent
