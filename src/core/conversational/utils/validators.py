"""
Validadores del Asistente.

Validacion de entrada para mensajes, sesiones,
personalidades y otros datos del usuario.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from .types.personality import PERSONALITY_PRESETS  # type: ignore[import-unresolved]
from ..config.constants import MAX_MESSAGES_PER_SESSION


def validate_message(message: str) -> tuple[bool, str]:
    """
    Valida un mensaje de usuario.

    Returns:
        (valido, error) — error vacio si es valido.
    """
    if not message or not message.strip():
        return False, "El mensaje no puede estar vacio"
    if len(message) > 10000:
        return False, "El mensaje excede el limite de 10000 caracteres"
    if len(message.strip()) < 1:
        return False, "El mensaje debe tener al menos 1 caracter"
    return True, ""


def validate_session_id(session_id: str) -> bool:
    """Valida que un session_id tenga formato UUID v4."""
    if not session_id:
        return False
    try:
        uuid.UUID(session_id, version=4)
        return True
    except ValueError:
        return False


def validate_personality_name(name: str) -> tuple[bool, str]:
    """Valida un nombre de personalidad."""
    if not name:
        return True, ""  # Default es aceptable
    if name in PERSONALITY_PRESETS:
        return True, ""
    # Nombres personalizados: alfanumerico + guion bajo, 2-30 chars
    if re.match(r'^[a-zA-Z0-9_]{2,30}$', name):
        return True, ""
    return False, f"Nombre de personalidad invalido: {name}"


def validate_language(lang: str) -> tuple[bool, str]:
    """Valida un codigo de idioma."""
    valid = {"es", "en", "bi"}
    if lang in valid:
        return True, ""
    return False, f"Idioma no soportado: {lang}. Validos: {valid}"


def validate_token_budget(
    messages_count: int,
    max_messages: int = MAX_MESSAGES_PER_SESSION,
) -> tuple[bool, str]:
    """Valida que no se exceda el presupuesto de mensajes."""
    if messages_count >= max_messages:
        return False, f"Limite de mensajes alcanzado ({max_messages})"
    return True, ""
