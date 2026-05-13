"""
Tipos de personalidad y tono del asistente.

Modela el perfil de personalidad configurable que define
como responde el asistente: tono, idioma, nivel tecnico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToneLevel(str, Enum):
    """Niveles de tono del asistente."""
    CASUAL = "casual"          # Informal, amigable
    PROFESSIONAL = "professional"  # Profesional, directo
    TECHNICAL = "technical"    # Tecnico, detallado
    FRIENDLY = "friendly"      # Calido, cercano
    FORMAL = "formal"          # Formal, respetuoso


class LanguagePreference(str, Enum):
    """Preferencia de idioma del usuario."""
    SPANISH = "es"
    ENGLISH = "en"
    BILINGUAL = "bi"   # Responde en el idioma de la pregunta


# ─── Personalidades predefinidas ─────────────────────────────

PERSONALITY_PRESETS: dict[str, dict[str, Any]] = {
    "zenic": {
        "name": "Zenic",
        "description": "Asistente equilibrado — profesional pero cercano",
        "default_tone": "professional",
        "greeting_es": "Hola, soy Zenic. En que puedo ayudarte?",
        "greeting_en": "Hi, I'm Zenic. How can I help you?",
        "traits": ["helpful", "precise", "bilingual"],
    },
    "logic": {
        "name": "Logic",
        "description": "Asistente tecnico — preciso y detallado",
        "default_tone": "technical",
        "greeting_es": "Sistema Logic listo. Especifica tu consulta.",
        "greeting_en": "Logic system ready. Specify your query.",
        "traits": ["analytical", "precise", "structured"],
    },
    "nova": {
        "name": "Nova",
        "description": "Asistente creativo — amigable y expresivo",
        "default_tone": "friendly",
        "greeting_es": "Hey! Soy Nova, tu asistente creativo. Que vamos a hacer hoy?",
        "greeting_en": "Hey! I'm Nova, your creative assistant. What are we doing today?",
        "traits": ["creative", "enthusiastic", "expressive"],
    },
}


@dataclass
class PersonalityProfile:
    """
    Perfil de personalidad del asistente.

    Define como el asistente se comunica: tono, idioma,
    nivel de detalle, saludo y rasgos de personalidad.
    """
    name: str = "zenic"
    tone: ToneLevel = ToneLevel.PROFESSIONAL
    language: LanguagePreference = LanguagePreference.BILINGUAL
    detail_level: int = 2         # 1=conciso, 2=normal, 3=detallado
    use_emoji: bool = False       # Usar emojis en respuestas
    code_comments: bool = True    # Incluir comentarios en codigo
    greeting: str = ""
    traits: list[str] = field(default_factory=lambda: ["helpful", "precise", "bilingual"])
    custom_instructions: str = ""  # Instrucciones adicionales del usuario
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Carga preset si el nombre coincide con uno predefinido."""
        if self.name in PERSONALITY_PRESETS and not self.greeting:
            preset = PERSONALITY_PRESETS[self.name]
            if not self.greeting:
                lang_key = "greeting_es" if self.language != LanguagePreference.ENGLISH else "greeting_en"
                self.greeting = preset.get(lang_key, "")
            if self.traits == ["helpful", "precise", "bilingual"]:
                self.traits = preset.get("traits", self.traits)
            if self.tone == ToneLevel.PROFESSIONAL and "default_tone" in preset:
                self.tone = ToneLevel(preset["default_tone"])

    @property
    def is_bilingual(self) -> bool:
        return self.language == LanguagePreference.BILINGUAL

    @property
    def is_technical(self) -> bool:
        return self.tone == ToneLevel.TECHNICAL

    @property
    def is_concise(self) -> bool:
        return self.detail_level == 1

    def get_system_prompt_suffix(self) -> str:
        """
        Genera un sufijo para el system prompt basado en la personalidad.

        Este sufijo se agrega al system prompt base del asistente
        para ajustar el comportamiento segun la personalidad.
        """
        parts: list[str] = []

        # Tono
        tone_instructions = {
            ToneLevel.CASUAL: "Responde de forma informal y amigable. Usa un tono conversacional.",
            ToneLevel.PROFESSIONAL: "Responde de forma profesional y directa. Se conciso pero completo.",
            ToneLevel.TECHNICAL: "Responde con detalle tecnico. Incluye especificaciones y referencias.",
            ToneLevel.FRIENDLY: "Responde con calidez y empatia. Se cercano sin perder precision.",
            ToneLevel.FORMAL: "Responde con formalidad y respeto. Usa un registro elevado.",
        }
        parts.append(tone_instructions.get(self.tone, ""))

        # Idioma
        if self.language == LanguagePreference.SPANISH:
            parts.append("Responde siempre en espanol.")
        elif self.language == LanguagePreference.ENGLISH:
            parts.append("Always respond in English.")
        else:
            parts.append("Responde en el idioma en que te hablen (espanol o ingles).")

        # Nivel de detalle
        detail_map = {
            1: "Se conciso. Respuestas breves y al punto.",
            2: "Proporciona respuestas de longitud normal con ejemplos cuando sea util.",
            3: "Se exhaustivo. Incluye explicaciones detalladas, ejemplos y contexto adicional.",
        }
        parts.append(detail_map.get(self.detail_level, detail_map[2]))

        # Emojis
        if self.use_emoji:
            parts.append("Puedes usar emojis moderadamente para hacer las respuestas mas expresivas.")

        # Custom instructions
        if self.custom_instructions:
            parts.append(f"Instrucciones adicionales del usuario: {self.custom_instructions}")

        return "\n".join(parts)

    @classmethod
    def from_preset(cls, name: str) -> PersonalityProfile:
        """Crea un perfil desde un preset predefinido."""
        preset = PERSONALITY_PRESETS.get(name, PERSONALITY_PRESETS["zenic"])
        return cls(
            name=name,
            tone=ToneLevel(preset.get("default_tone", "professional")),
            traits=preset.get("traits", ["helpful", "precise", "bilingual"]),
        )
