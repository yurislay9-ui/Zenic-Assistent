"""
Handlers del pipeline del Asistente.

Cada handler procesa un tipo de pipeline especifico:
  - Conversacional: chat general, feedback
  - Preguntas: preguntas factuales con contexto de memoria
  - Comandos: comandos directos del usuario
  - Config: cambios de configuracion
  - Engine: procesamiento via motor Zenic-Agents
"""

from __future__ import annotations

from typing import Any, Optional

from ..types.base import Result, Ok
from ..types.session import Session
from ..types.intent import AssistantIntent, IntentCategory
from ..types.response import (
    AssistantResponse, ResponseFormat, ResponseMetadata,
)
from ..types.personality import PersonalityProfile
from .engine_parts import ResponseGenerator, EngineFormatter
from .zenic_bridge import ZenicBridge


class PipelineHandlers:
    """
    Handlers para cada tipo de pipeline.

    Cada metodo retorna un AssistantResponse completo.
    Separados del ConversationEngine para mantener
    el archivo principal bajo 400 lineas.
    """

    def __init__(
        self,
        generator: ResponseGenerator,
        formatter: EngineFormatter,
        personality_getter: Any,  # Callable para obtener default personality
        bridge: Optional[ZenicBridge] = None,
    ) -> None:
        self._generator = generator
        self._formatter = formatter
        self._get_personality = personality_getter
        self._bridge = bridge

    # ─── Conversacional ───────────────────────────────────────

    def handle_conversational(
        self,
        message: str,
        intent: AssistantIntent,
        session: Session,
        personality: Optional[PersonalityProfile] = None,
    ) -> AssistantResponse:
        """Maneja mensajes conversacionales sin motor."""
        profile = personality or self._get_personality()
        text = message.lower().strip()

        if intent.category == IntentCategory.CHAT:
            content = self._generator.generate_chat(text, profile, session)
        elif intent.category == IntentCategory.FEEDBACK:
            content = self._generator.handle_feedback(text, profile)
        else:
            content = self._generator.generate_chat(text, profile, session)

        fmt = ResponseFormat.MARKDOWN
        if "```" in content:
            fmt = ResponseFormat.MIXED

        return AssistantResponse(
            content=content, format=fmt,
            metadata=ResponseMetadata(source="deterministic"),
        )

    # ─── Preguntas ────────────────────────────────────────────

    def handle_question(
        self,
        enriched: Any,
        intent: AssistantIntent,
        session: Session,
        personality: Optional[PersonalityProfile] = None,
    ) -> AssistantResponse:
        """Maneja preguntas con contexto de memoria."""
        profile = personality or self._get_personality()
        content = self._generator.generate_question(enriched.text, profile)

        # Enriquecer con memoria si hay
        if enriched.has_context:
            memory_ctx = enriched.memory_context[:2]
            memory_str = "\n".join(
                f"- {m.get('content', '')}" for m in memory_ctx
            )
            if memory_str:
                content += f"\n\n*Contexto relevante:*\n{memory_str}"

        return AssistantResponse(
            content=content,
            format=ResponseFormat.MARKDOWN,
            metadata=ResponseMetadata(source="deterministic"),
        )

    # ─── Comandos ─────────────────────────────────────────────

    def handle_command(self, enriched: Any, session: Session) -> AssistantResponse:
        """Maneja comandos directos."""
        content = self._generator.handle_command(enriched.normalized, session)
        return AssistantResponse(
            content=content,
            format=ResponseFormat.MARKDOWN,
            metadata=ResponseMetadata(source="command"),
        )

    # ─── Configuracion ────────────────────────────────────────

    def handle_config(self, enriched: Any, session: Session) -> AssistantResponse:
        """Maneja cambios de configuracion."""
        content = self._generator.handle_config(enriched.normalized, session)
        return AssistantResponse(
            content=content,
            format=ResponseFormat.MARKDOWN,
            metadata=ResponseMetadata(source="config"),
        )

    # ─── Engine ───────────────────────────────────────────────

    async def handle_engine(
        self,
        message: str,
        intent: AssistantIntent,
        session: Session,
        personality: Optional[PersonalityProfile] = None,
    ) -> AssistantResponse:
        """Maneja mensajes que requieren el motor Zenic-Agents."""
        if self._bridge is None or not self._bridge.is_available:
            return AssistantResponse.from_error(
                "Motor Zenic-Agents no disponible. "
                "Funcionando en modo conversacional.",
                source="fallback",
            )

        engine_result = await self._bridge.execute(message)
        profile = personality or self._get_personality()
        content = self._formatter.format(engine_result, profile)

        return AssistantResponse(
            content=content, format=ResponseFormat.MIXED,
            metadata=ResponseMetadata(source="engine", engine_used=True),
        )

    # ─── Fallback ─────────────────────────────────────────────

    @staticmethod
    async def fallback_handler(
        ctx: Any,
    ) -> Result[AssistantResponse]:
        """Handler de fallback conversacional garantizado."""
        lang = ctx.metadata.get("language", "es") if ctx.metadata else "es"
        if lang == "en":
            content = "I'm here to help. Could you rephrase your request?"
        else:
            content = "Estoy aqui para ayudar. Podrias reformular tu solicitud?"

        return Ok(AssistantResponse(
            content=content,
            format=ResponseFormat.MARKDOWN,
            metadata=ResponseMetadata(source="fallback"),
        ))
