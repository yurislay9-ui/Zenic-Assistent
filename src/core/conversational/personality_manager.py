"""
Gestor de personalidad del asistente.

Maneja perfiles de personalidad, permite cambiar entre
presets y crear perfiles personalizados.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..types.personality import (
    PersonalityProfile,
    ToneLevel,
    LanguagePreference,
    PERSONALITY_PRESETS,
)

logger = logging.getLogger("zenic_agents.conversational.personality")


class PersonalityManager:
    """
    Gestiona los perfiles de personalidad del asistente.

    Permite:
      - Obtener perfiles predefinidos (zenic, logic, nova)
      - Crear perfiles personalizados
      - Cambiar tono e idioma en runtime
      - Generar system prompts basados en personalidad
    """

    def __init__(self) -> None:
        self._profiles: dict[str, PersonalityProfile] = {}
        self._default_name: str = "zenic"
        self._load_presets()

    def _load_presets(self) -> None:
        """Carga los presets predefinidos."""
        for name in PERSONALITY_PRESETS:
            self._profiles[name] = PersonalityProfile.from_preset(name)
        logger.info(f"Personalidades cargadas: {list(self._profiles.keys())}")

    # ─── Lectura ──────────────────────────────────────────────

    def get(self, name: str) -> Optional[PersonalityProfile]:
        """Obtiene un perfil por nombre."""
        return self._profiles.get(name)

    def get_default(self) -> PersonalityProfile:
        """Obtiene el perfil por defecto."""
        return self._profiles.get(
            self._default_name,
            PersonalityProfile(),
        )

    def list_profiles(self) -> list[str]:
        """Lista los nombres de perfiles disponibles."""
        return list(self._profiles.keys())

    def get_profile_info(self, name: str) -> dict:
        """Obtiene informacion resumida de un perfil."""
        profile = self._profiles.get(name)
        if profile is None:
            return {"error": f"Perfil '{name}' no encontrado"}
        return {
            "name": profile.name,
            "tone": profile.tone.value,
            "language": profile.language.value,
            "detail_level": profile.detail_level,
            "traits": profile.traits,
            "greeting": profile.greeting,
        }

    # ─── Modificacion ─────────────────────────────────────────

    def set_default(self, name: str) -> bool:
        """Cambia el perfil por defecto. Retorna True si existe."""
        if name in self._profiles:
            self._default_name = name
            logger.info(f"Personalidad por defecto cambiada a: {name}")
            return True
        return False

    def create_profile(self, profile: PersonalityProfile) -> None:
        """Crea o reemplaza un perfil personalizado."""
        self._profiles[profile.name] = profile
        logger.info(f"Perfil creado/actualizado: {profile.name}")

    def update_tone(self, name: str, tone: ToneLevel) -> bool:
        """Actualiza el tono de un perfil existente."""
        profile = self._profiles.get(name)
        if profile is None:
            return False
        profile.tone = tone
        return True

    def update_language(self, name: str, lang: LanguagePreference) -> bool:
        """Actualiza el idioma de un perfil existente."""
        profile = self._profiles.get(name)
        if profile is None:
            return False
        profile.language = lang
        return True

    def set_custom_instructions(self, name: str, instructions: str) -> bool:
        """Establece instrucciones personalizadas para un perfil."""
        profile = self._profiles.get(name)
        if profile is None:
            return False
        profile.custom_instructions = instructions
        return True

    # ─── System prompt ────────────────────────────────────────

    def build_system_prompt(
        self,
        personality_name: Optional[str] = None,
        session_context: str = "",
    ) -> str:
        """
        Construye el system prompt completo para una sesion.

        Combina:
          1. System prompt base del asistente
          2. Sufijo de personalidad
          3. Contexto de sesion (si hay)
        """
        profile = self._profiles.get(
            personality_name or self._default_name,
            PersonalityProfile(),
        )

        # Base prompt
        base = (
            "Eres Zenic-Agents Asistente, un asistente inteligente construido "
            "sobre un motor de IA quirurgico con 48 agentes especializados. "
            "Tu arquitectura garantiza respuestas deterministas con fallbacks, "
            "y la IA solo se usa como arbitro binario (SI/NO) cuando es necesario.\n\n"
        )

        # Personality suffix
        suffix = profile.get_system_prompt_suffix()

        # Session context
        context_part = ""
        if session_context:
            context_part = f"\n\nContexto de la sesion:\n{session_context}"

        return base + suffix + context_part
