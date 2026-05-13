"""
Tipos de intencion del asistente.

Extiende los tipos de Zenic-Agents con categorias de intencion
orientadas a conversacion: chat, preguntas, comandos, tareas,
configuracion y feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentCategory(str, Enum):
    """
    Categorias de intencion del asistente.

    Extiende las operaciones de Zenic-Agents (CREATE, REFACTOR, etc.)
    con categorias conversacionales que no existian en el motor
    quirurgico original.
    """
    # Conversacionales (nuevas para asistente)
    CHAT = "chat"                # Conversacion general
    QUESTION = "question"        # Pregunta factual o explicativa
    COMMAND = "command"          # Comando directo (ej: "limpiar", "reset")
    FEEDBACK = "feedback"        # Feedback del usuario sobre respuesta
    CONFIG = "config"            # Cambio de configuracion

    # Heredadas de Zenic-Agents (mapean a operaciones del motor)
    CODE_CREATE = "code_create"      # Mapea a CREATE
    CODE_REFACTOR = "code_refactor"  # Mapea a REFACTOR
    CODE_DEBUG = "code_debug"        # Mapea a DEBUG
    CODE_OPTIMIZE = "code_optimize"  # Mapea a OPTIMIZE
    CODE_ANALYZE = "code_analyze"    # Mapea a ANALYZE
    CODE_EXPLAIN = "code_explain"    # Mapea a EXPLAIN

    # Operaciones de negocio (mapean a capa 3)
    BUSINESS = "business"            # Operaciones de negocio
    AUTOMATION = "automation"        # Automatizaciones

    # Especiales
    UNKNOWN = "unknown"              # No se pudo clasificar
    MULTI = "multi"                  # Multiples intenciones en un mensaje


class ConversationMode(str, Enum):
    """Modo de conversacion del asistente."""
    NORMAL = "normal"          # Conversacion estandar
    CODING = "coding"          # Modo enfocado en codigo
    REASONING = "reasoning"    # Modo de razonamiento paso a paso
    TEACHING = "teaching"      # Modo de ensenanza/explicacion
    AUTOMATION = "automation"  # Configuracion de automatizaciones


@dataclass
class AssistantIntent:
    """
    Intencion detectada del usuario en contexto de asistente.

    Combina la clasificacion original de Zenic-Agents con
    las nuevas categorias conversacionales.
    """
    category: IntentCategory = IntentCategory.UNKNOWN
    operation: str = ""        # Operacion original de Zenic-Agents (CREATE, etc.)
    goal: str = ""             # Goal original (FEATURE_ADD, etc.)
    confidence: float = 0.0
    mode: ConversationMode = ConversationMode.NORMAL
    entities: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    language: str = "es"
    source: str = "deterministic"

    @property
    def is_conversational(self) -> bool:
        """True si la intencion es puramente conversacional."""
        return self.category in (
            IntentCategory.CHAT,
            IntentCategory.QUESTION,
            IntentCategory.FEEDBACK,
            IntentCategory.CONFIG,
        )

    @property
    def is_code_related(self) -> bool:
        """True si la intencion involucra codigo."""
        return self.category in (
            IntentCategory.CODE_CREATE,
            IntentCategory.CODE_REFACTOR,
            IntentCategory.CODE_DEBUG,
            IntentCategory.CODE_OPTIMIZE,
            IntentCategory.CODE_ANALYZE,
            IntentCategory.CODE_EXPLAIN,
        )

    @property
    def needs_engine(self) -> bool:
        """True si necesita pasar por el motor de Zenic-Agents."""
        return self.is_code_related or self.category in (
            IntentCategory.BUSINESS,
            IntentCategory.AUTOMATION,
        )

    def to_zenic_operation(self) -> str:
        """Mapea la categoria a la operacion de Zenic-Agents."""
        mapping = {
            IntentCategory.CODE_CREATE: "CREATE",
            IntentCategory.CODE_REFACTOR: "REFACTOR",
            IntentCategory.CODE_DEBUG: "DEBUG",
            IntentCategory.CODE_OPTIMIZE: "OPTIMIZE",
            IntentCategory.CODE_ANALYZE: "ANALYZE",
            IntentCategory.CODE_EXPLAIN: "EXPLAIN",
            IntentCategory.BUSINESS: "ANALYZE",
            IntentCategory.AUTOMATION: "CREATE",
        }
        return mapping.get(self.category, "SEARCH")


@dataclass
class IntentResult:
    """Resultado del proceso de deteccion de intencion."""
    intent: AssistantIntent = field(default_factory=AssistantIntent)
    alternative_intents: list[AssistantIntent] = field(default_factory=list)
    context_keywords: list[str] = field(default_factory=list)
    source: str = "deterministic"
    processing_time_ms: float = 0.0
