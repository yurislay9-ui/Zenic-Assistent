"""
Handlers adicionales del pipeline del asistente.

Contiene los handlers de pipeline especificos de Fase 2
que no estaban en el pipeline_handlers original.
"""

from __future__ import annotations

from typing import Any, Optional

from .types.intent import AssistantIntent
from .types.session import Session
from .types.response import AssistantResponse, ResponseFormat, ResponseMetadata
from .types.personality import PersonalityProfile
from .tools import ToolManager


class Phase2Handlers:
    """
    Handlers de pipeline para capacidades de Fase 2.

    Manejan tool pipeline, knowledge enrichment
    y otros flujos especificos de Fase 2.
    """

    def __init__(self, tool_manager: ToolManager) -> None:
        self._tools = tool_manager

    async def handle_tool_pipeline(
        self,
        enriched: Any,
        intent: AssistantIntent,
        session: Session,
        personality: Optional[PersonalityProfile] = None,
    ) -> AssistantResponse:
        """Maneja el pipeline de ejecucion de herramientas."""
        # Buscar tools relevantes
        tools = self._tools.get_tools_for_intent(intent)
        if not tools:
            # Fallback a conversacional
            from .engine_parts import ResponseGenerator
            from .personality_manager import PersonalityManager
            gen = ResponseGenerator()
            profile = personality or PersonalityManager().get_default()
            content = gen.generate_chat(
                enriched.text.lower().strip(), profile, session,
            )
            return AssistantResponse(
                content=content,
                format=ResponseFormat.MARKDOWN,
                metadata=ResponseMetadata(source="conversational"),
            )

        tool_names = ", ".join(t.name for t in tools)
        content = (
            f"Puedo usar las siguientes herramientas para ayudarte: "
            f"{tool_names}.\n\n"
            f"Tu solicitud fue: *{enriched.text[:100]}*\n\n"
            f"En una version futura, ejecutare la herramienta mas "
            f"adecuada automaticamente."
        )

        return AssistantResponse(
            content=content,
            format=ResponseFormat.MARKDOWN,
            metadata=ResponseMetadata(source="tool_pipeline"),
        )
