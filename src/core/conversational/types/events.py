"""
Tipos de eventos del Asistente.

Sistema de eventos tipado para desacoplar componentes.
Cada evento tiene tipo, payload, y metadata de trazabilidad.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .base import EventId, SessionId, new_id


# ─── Tipos de evento ─────────────────────────────────────────

class EventType(str, Enum):
    """Tipos de eventos del sistema."""
    # Pipeline
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_PROCESSED = "message_processed"
    INTENT_CLASSIFIED = "intent_classified"
    ROUTE_SELECTED = "route_selected"
    RESPONSE_GENERATED = "response_generated"
    RESPONSE_SENT = "response_sent"

    # Memoria
    MEMORY_STORED = "memory_stored"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_EVICTED = "memory_evicted"

    # Tools
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"

    # Sesion
    SESSION_CREATED = "session_created"
    SESSION_ENDED = "session_ended"
    SESSION_EXPIRED = "session_expired"

    # Sistema
    ERROR_OCCURRED = "error_occurred"
    HEALTH_CHECK = "health_check"
    CONFIG_CHANGED = "config_changed"


# ─── Evento ───────────────────────────────────────────────────

@dataclass
class Event:
    """
    Evento inmutable del sistema.

    Los eventos son la unidad de comunicacion entre componentes.
    Se emiten despues de que algo sucede (never before).
    """
    event_id: EventId = field(default_factory=lambda: new_id("evt"))
    event_type: EventType = EventType.MESSAGE_RECEIVED
    session_id: SessionId = ""
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""              # Componente que emitio el evento
    correlation_id: str = ""      # Para rastrear un request a traves del pipeline
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_ms(self) -> float:
        """Edad del evento en milisegundos."""
        return (time.time() - self.timestamp) * 1000


# ─── Handler de eventos ──────────────────────────────────────

type EventHandler = Callable[[Event], None]
type AsyncEventHandler = Callable[[Event], Any]


# ─── Subscription ─────────────────────────────────────────────

@dataclass
class Subscription:
    """
    Suscripcion a un tipo de evento.

    Mantiene la referencia al handler y permite desuscribirse.
    """
    sub_id: str = field(default_factory=lambda: new_id("sub"))
    event_type: EventType = EventType.MESSAGE_RECEIVED
    handler: EventHandler | None = None
    async_handler: AsyncEventHandler | None = None
    filter_fn: Callable[[Event], bool] | None = None
    priority: int = 0             # Mayor = se ejecuta primero
    active: bool = True

    def matches(self, event: Event) -> bool:
        """Verifica si el evento matchea esta suscripcion."""
        if not self.active:
            return False
        if event.event_type != self.event_type:
            return False
        if self.filter_fn and not self.filter_fn(event):
            return False
        return True


# ─── Evento especificos del pipeline ─────────────────────────

@dataclass
class MessageReceivedPayload:
    """Payload para MESSAGE_RECEIVED."""
    user_message: str = ""
    session_id: SessionId = ""
    language: str = "es"


@dataclass
class IntentClassifiedPayload:
    """Payload para INTENT_CLASSIFIED."""
    category: str = ""
    confidence: float = 0.0
    mode: str = ""
    is_conversational: bool = True
    needs_engine: bool = False


@dataclass
class ResponseGeneratedPayload:
    """Payload para RESPONSE_GENERATED."""
    content_length: int = 0
    format: str = "markdown"
    source: str = "deterministic"
    latency_ms: float = 0.0
    tools_used: list[str] = field(default_factory=list)


@dataclass
class ToolCalledPayload:
    """Payload para TOOL_CALLED."""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ErrorPayload:
    """Payload para ERROR_OCCURRED."""
    error_type: str = ""
    error_message: str = ""
    component: str = ""
    recoverable: bool = True
