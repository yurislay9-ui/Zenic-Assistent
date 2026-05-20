"""
Helpers del Asistente.

Funciones auxiliares reutilizables: truncado,
estimacion de tokens, formateo y generacion de IDs.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

# Phase 5 — Deterministic ID generation
from src.core.shared.deterministic import FencingTokenGenerator


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Trunca texto a una longitud maxima con sufijo."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def count_tokens_approx(text: str) -> int:
    """
    Estimacion aproximada de tokens.

    Regla: ~4 caracteres = 1 token (promedio ingles/espanol).
    No es exacto pero suficiente para budgeting de contexto.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def format_duration(ms: float) -> str:
    """Formatea milisegundos en formato legible."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    return f"{minutes:.1f}m"


def safe_json(obj: Any, default: str = "{}") -> str:
    """Serializa a JSON de forma segura (no lanza excepciones)."""
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return default


# Module-level fencing token generator for deterministic IDs
_id_fencing = FencingTokenGenerator("generate_id")


def generate_id(prefix: str = "") -> str:
    """Genera un ID unico con prefijo opcional.

    Phase 5: Uses FencingTokenGenerator for deterministic timestamps
    instead of time.time()*1000.
    """
    uid = str(uuid.uuid4())[:8]
    timestamp = str(_id_fencing.next())[-6:]
    if prefix:
        return f"{prefix}_{uid}_{timestamp}"
    return f"{uid}_{timestamp}"
