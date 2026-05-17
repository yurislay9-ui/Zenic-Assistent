"""
Enriquecedor de entrada del Asistente.

Enriquece el input parseado con:
  - Contexto de sesion (mensajes recientes)
  - Contexto de memoria (recuerdos relevantes)
  - Contexto de personalidad (tono, idioma)
  - Prioridad ajustada por historial

El enricher es la ultima etapa antes de clasificacion de intencion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..types.base import Result, Ok, PipelineContext, Priority
from ..types.session import Session, MessageRole
from .sanitizer import SanitizedInput
from .parser import ParsedInput


# ─── Protocolo de fuente de contexto ─────────────────────────

@runtime_checkable
class ContextSource(Protocol):
    """Fuente de contexto para enriquecimiento."""

    def get_context(self, session_id: str, query: str) -> list[dict[str, Any]]:
        """Obtiene contexto relevante para una query y sesion."""
        ...


# ─── Contexto enriquecido ────────────────────────────────────

@dataclass
class EnrichedInput:
    """Input completamente procesado y enriquecido."""
    sanitized: SanitizedInput = field(default_factory=SanitizedInput)
    parsed: ParsedInput = field(default_factory=ParsedInput)
    session_context: list[dict[str, Any]] = field(default_factory=list)
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    conversation_turn: int = 0
    recent_topics: list[str] = field(default_factory=list)
    user_preferences: dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL

    @property
    def text(self) -> str:
        """Texto limpio listo para procesamiento."""
        return self.sanitized.cleaned

    @property
    def normalized(self) -> str:
        """Texto normalizado para matching."""
        return self.parsed.normalized

    @property
    def has_context(self) -> bool:
        """True si hay contexto de sesion o memoria."""
        return len(self.session_context) > 0 or len(self.memory_context) > 0

    @property
    def is_continuation(self) -> bool:
        """True si parece una continuacion de conversacion previa."""
        return self.conversation_turn > 1 and not self.parsed.is_greeting

    def to_pipeline_context(self) -> PipelineContext:
        """Convierte a PipelineContext para el flujo principal."""
        return PipelineContext(
            user_message=self.sanitized.original,
            normalized_message=self.parsed.normalized,
            memory_context=self.memory_context,
            priority=self.priority,
            metadata={
                "language": self.sanitized.detected_language,
                "is_question": self.parsed.is_question,
                "is_command": self.parsed.is_command,
                "is_greeting": self.parsed.is_greeting,
                "is_code_request": self.parsed.is_code_request,
                "has_code": self.parsed.has_code,
                "conversation_turn": self.conversation_turn,
                "recent_topics": self.recent_topics,
                "entities": [
                    {"text": e.text, "type": e.entity_type}
                    for e in self.parsed.entities
                ],
                "keywords": self.parsed.keywords[:20],
                "warnings": self.sanitized.warnings,
            },
        )


class InputEnricher:
    """
    Enriquecedor de entrada.

    Combina datos de sanitizacion, parsing y fuentes de contexto
    para crear un EnrichedInput completo listo para clasificacion.
    """

    def __init__(self) -> None:
        self._context_sources: list[ContextSource] = []

    def register_source(self, source: ContextSource) -> None:
        """Registra una fuente de contexto."""
        self._context_sources.append(source)

    def enrich(
        self,
        sanitized: SanitizedInput,
        parsed: ParsedInput,
        session: Session | None = None,
        memory_entries: list[dict[str, Any]] | None = None,
    ) -> Result[EnrichedInput, Exception]:
        """
        Enriquece el input con contexto de sesion y memoria.

        Pipeline: session → memory → sources → compute → merge.
        """
        # 1. Contexto de sesion
        session_ctx = self._extract_session_context(session)
        turn = self._compute_turn(session)
        topics = self._extract_recent_topics(session)
        prefs = self._extract_preferences(session, sanitized)

        # 2. Contexto de memoria
        memory_ctx = memory_entries or []

        # 3. Fuentes externas
        external_ctx: list[dict[str, Any]] = []
        for source in self._context_sources:
            try:
                ctx = source.get_context(
                    session_id=session.session_id if session else "",
                    query=sanitized.cleaned,
                )
                external_ctx.extend(ctx)
            except Exception:
                continue  # Fuentes externas no deben romper el pipeline

        # 4. Ajustar prioridad
        priority = self._adjust_priority(
            sanitized.priority, turn, memory_ctx, parsed
        )

        # 5. Merge
        all_memory = memory_ctx + external_ctx

        return Ok(EnrichedInput(
            sanitized=sanitized,
            parsed=parsed,
            session_context=session_ctx,
            memory_context=all_memory,
            conversation_turn=turn,
            recent_topics=topics,
            user_preferences=prefs,
            priority=priority,
        ))

    # ─── Extraccion de contexto ───────────────────────────────

    @staticmethod
    def _extract_session_context(session: Session | None) -> list[dict[str, Any]]:
        """Extrae contexto de la sesion actual."""
        if session is None:
            return []

        recent = session.get_recent_messages(10)
        context: list[dict[str, Any]] = []
        for msg in recent:
            if msg.role in (MessageRole.USER, MessageRole.ASSISTANT):
                context.append({
                    "role": msg.role.value,
                    "content": msg.content[:200],  # Truncar para no saturar
                    "source": "session",
                })
        return context

    @staticmethod
    def _compute_turn(session: Session | None) -> int:
        """Calcula el numero de turno de conversacion."""
        if session is None:
            return 0
        return len([m for m in session.messages if m.is_user])

    @staticmethod
    def _extract_recent_topics(session: Session | None) -> list[str]:
        """Extrae topics recientes de la sesion."""
        if session is None:
            return []

        # Extraer keywords de los ultimos mensajes del asistente
        topics: list[str] = []
        for msg in session.get_recent_messages(5):
            if msg.is_assistant:
                # Tomar palabras significativas del inicio
                words = msg.content.split()[:5]
                for w in words:
                    w_clean = w.strip("*,.`!?:;\"'()[]{}")
                    if len(w_clean) > 3:
                        topics.append(w_clean.lower())
        return topics[:10]

    @staticmethod
    def _extract_preferences(
        session: Session | None, sanitized: SanitizedInput
    ) -> dict[str, Any]:
        """Extrae preferencias del usuario de la sesion."""
        prefs: dict[str, Any] = {}
        if session:
            prefs["language"] = session.config.language
            prefs["tone"] = session.config.tone
            prefs["personality"] = session.config.personality_name
        prefs["detected_language"] = sanitized.detected_language
        return prefs

    @staticmethod
    def _adjust_priority(
        base: Priority,
        turn: int,
        memory_ctx: list[dict[str, Any]],
        parsed: ParsedInput,
    ) -> Priority:
        """Ajusta la prioridad basado en contexto."""
        # Conversaciones largas = prioridad normal
        if base == Priority.CRITICAL:
            return Priority.CRITICAL

        # Code requests en contexto continuo = HIGH
        if parsed.is_code_request and turn > 1:
            return Priority.HIGH

        # Si hay contexto de memoria relevante, subir prioridad
        if len(memory_ctx) >= 3:
            return Priority.HIGH

        return base
