"""
Helpers para emision de eventos tipados.

Provee funciones helper para emitir eventos comunes
con payloads correctamente tipados.
"""

from __future__ import annotations

from typing import Any

from ...types.events import (
    Event, EventType,
    MessageReceivedPayload,
    IntentClassifiedPayload,
    ResponseGeneratedPayload,
    ToolCalledPayload,
    ErrorPayload,
)
from .event_bus import EventBus


class EventTypes:
    """
    Helpers para emitir eventos tipados.

    Cada metodo emite un evento con el payload
    correctamente estructurado.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def message_received(
        self,
        session_id: str,
        user_message: str,
        language: str = "es",
        source: str = "input",
    ) -> Event:
        """Emite evento de mensaje recibido."""
        payload = MessageReceivedPayload(
            user_message=user_message,
            session_id=session_id,
            language=language,
        )
        return self._bus.emit(
            event_type=EventType.MESSAGE_RECEIVED,
            payload={
                "user_message": payload.user_message,
                "session_id": payload.session_id,
                "language": payload.language,
            },
            session_id=session_id,
            source=source,
        )

    def intent_classified(
        self,
        session_id: str,
        category: str,
        confidence: float,
        mode: str = "",
        is_conversational: bool = True,
        needs_engine: bool = False,
        source: str = "intent_engine",
    ) -> Event:
        """Emite evento de intencion clasificada."""
        payload = IntentClassifiedPayload(
            category=category,
            confidence=confidence,
            mode=mode,
            is_conversational=is_conversational,
            needs_engine=needs_engine,
        )
        return self._bus.emit(
            event_type=EventType.INTENT_CLASSIFIED,
            payload={
                "category": payload.category,
                "confidence": payload.confidence,
                "mode": payload.mode,
                "is_conversational": payload.is_conversational,
                "needs_engine": payload.needs_engine,
            },
            session_id=session_id,
            source=source,
        )

    def response_generated(
        self,
        session_id: str,
        content_length: int,
        fmt: str = "markdown",
        resp_source: str = "deterministic",
        latency_ms: float = 0.0,
        tools_used: list[str] | None = None,
        source: str = "response",
    ) -> Event:
        """Emite evento de respuesta generada."""
        payload = ResponseGeneratedPayload(
            content_length=content_length,
            format=fmt,
            source=resp_source,
            latency_ms=latency_ms,
            tools_used=tools_used or [],
        )
        return self._bus.emit(
            event_type=EventType.RESPONSE_GENERATED,
            payload={
                "content_length": payload.content_length,
                "format": payload.format,
                "source": payload.source,
                "latency_ms": payload.latency_ms,
                "tools_used": payload.tools_used,
            },
            session_id=session_id,
            source=source,
        )

    def tool_called(
        self,
        session_id: str,
        tool_name: str,
        call_id: str = "",
        arguments: dict[str, Any] | None = None,
        source: str = "tool_executor",
    ) -> Event:
        """Emite evento de tool llamada."""
        payload = ToolCalledPayload(
            tool_name=tool_name,
            call_id=call_id,
            arguments=arguments or {},
        )
        return self._bus.emit(
            event_type=EventType.TOOL_CALLED,
            payload={
                "tool_name": payload.tool_name,
                "call_id": payload.call_id,
                "arguments": payload.arguments,
            },
            session_id=session_id,
            source=source,
        )

    def error_occurred(
        self,
        session_id: str,
        error_type: str,
        error_message: str,
        component: str = "",
        recoverable: bool = True,
        source: str = "error_handler",
    ) -> Event:
        """Emite evento de error."""
        payload = ErrorPayload(
            error_type=error_type,
            error_message=error_message,
            component=component,
            recoverable=recoverable,
        )
        return self._bus.emit(
            event_type=EventType.ERROR_OCCURRED,
            payload={
                "error_type": payload.error_type,
                "error_message": payload.error_message,
                "component": payload.component,
                "recoverable": payload.recoverable,
            },
            session_id=session_id,
            source=source,
        )

    def session_created(
        self, session_id: str, source: str = "session_manager"
    ) -> Event:
        """Emite evento de sesion creada."""
        return self._bus.emit(
            event_type=EventType.SESSION_CREATED,
            payload={"session_id": session_id},
            session_id=session_id,
            source=source,
        )

    def session_ended(
        self, session_id: str, source: str = "session_manager"
    ) -> Event:
        """Emite evento de sesion terminada."""
        return self._bus.emit(
            event_type=EventType.SESSION_ENDED,
            payload={"session_id": session_id},
            session_id=session_id,
            source=source,
        )

    def memory_stored(
        self,
        session_id: str,
        category: str,
        importance: float,
        source: str = "memory",
    ) -> Event:
        """Emite evento de memoria almacenada."""
        return self._bus.emit(
            event_type=EventType.MEMORY_STORED,
            payload={
                "category": category,
                "importance": importance,
            },
            session_id=session_id,
            source=source,
        )
