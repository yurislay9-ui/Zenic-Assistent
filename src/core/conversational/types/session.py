"""
Tipos de sesion conversacional.

Modela sesiones de usuario, mensajes, estados y configuracion.
Cada sesion es independiente y tiene su propio historial,
contexto y preferencias.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── Identificadores ──────────────────────────────────────────

type SessionId = str  # UUID v4 string


def new_session_id() -> SessionId:
    """Genera un nuevo session ID unico."""
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────

class SessionState(str, Enum):
    """Estados posibles de una sesion de conversacion."""
    ACTIVE = "active"
    IDLE = "idle"          # Sin actividad reciente
    PAUSED = "paused"      # Pausada por el usuario
    ENDED = "ended"        # Sesion terminada
    ERROR = "error"        # Sesion en estado de error


class MessageRole(str, Enum):
    """Roles de los mensajes en la conversacion."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"          # Resultado de tool execution


# ─── Metadata ─────────────────────────────────────────────────

@dataclass
class MessageMetadata:
    """Metadata adjunta a un mensaje."""
    timestamp: float = 0.0
    latency_ms: float = 0.0
    token_count: int = 0
    intent_category: str = ""
    route_taken: str = ""
    source: str = "deterministic"
    error: str = ""

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ─── Mensaje ──────────────────────────────────────────────────

@dataclass
class Message:
    """Mensaje individual dentro de una conversacion."""
    role: MessageRole = MessageRole.USER
    content: str = ""
    metadata: MessageMetadata = field(default_factory=MessageMetadata)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_user(self) -> bool:
        return self.role == MessageRole.USER

    @property
    def is_assistant(self) -> bool:
        return self.role == MessageRole.ASSISTANT

    @property
    def is_system(self) -> bool:
        return self.role == MessageRole.SYSTEM

    @property
    def is_tool(self) -> bool:
        return self.role == MessageRole.TOOL

    def to_openai_format(self) -> dict[str, Any]:
        """Convierte a formato OpenAI chat completion message."""
        msg: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_results:
            msg["tool_results"] = self.tool_results
        return msg


# ─── Configuracion de sesion ─────────────────────────────────

@dataclass
class SessionConfig:
    """Configuracion de una sesion individual."""
    max_history_messages: int = 100
    max_context_tokens: int = 4000
    idle_timeout_seconds: int = 1800  # 30 minutos
    language: str = "es"               # Idioma preferido
    tone: str = "professional"         # Tono del asistente
    streaming_enabled: bool = True
    tools_enabled: bool = True
    memory_enabled: bool = True
    personality_name: str = "zenic"    # Perfil de personalidad


# ─── Sesion ───────────────────────────────────────────────────

@dataclass
class Session:
    """
    Sesion de conversacion completa.

    Contiene historial de mensajes, estado, configuracion
    y datos de telemetria de la sesion.
    """
    session_id: SessionId = field(default_factory=new_session_id)
    user_id: str = ""
    state: SessionState = SessionState.ACTIVE
    config: SessionConfig = field(default_factory=SessionConfig)
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Propiedades utiles ──

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def is_active(self) -> bool:
        return self.state == SessionState.ACTIVE

    @property
    def is_expired(self) -> bool:
        """Verifica si la sesion ha expirado por inactividad."""
        if self.state in (SessionState.ENDED, SessionState.PAUSED):
            return False
        elapsed = time.time() - self.last_activity
        return elapsed > self.config.idle_timeout_seconds

    # ── Metodos de mensaje ──

    def add_message(self, message: Message) -> None:
        """Agrega un mensaje y actualiza la actividad."""
        self.messages.append(message)
        self.last_activity = time.time()
        # Truncar historial si excede el limite
        if len(self.messages) > self.config.max_history_messages:
            # Mantener system messages + ultimos N mensajes
            self._truncate_history()

    def get_recent_messages(self, count: int = 20) -> list[Message]:
        """Retorna los ultimos N mensajes de la conversacion."""
        return self.messages[-count:]

    def get_user_messages(self) -> list[Message]:
        """Filtra solo los mensajes del usuario."""
        return [m for m in self.messages if m.is_user]

    def get_assistant_messages(self) -> list[Message]:
        """Filtra solo los mensajes del asistente."""
        return [m for m in self.messages if m.is_assistant]

    def to_openai_messages(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """Convierte historial a formato OpenAI para context window."""
        recent = self.get_recent_messages(max_messages)
        return [m.to_openai_format() for m in recent]

    # ── Control de estado ──

    def activate(self) -> None:
        """Activa una sesion inactiva o pausada."""
        self.state = SessionState.ACTIVE
        self.last_activity = time.time()

    def pause(self) -> None:
        """Pausa la sesion."""
        self.state = SessionState.PAUSED

    def end(self) -> None:
        """Termina la sesion."""
        self.state = SessionState.ENDED

    def set_error(self, error_msg: str) -> None:
        """Marca la sesion en estado de error."""
        self.state = SessionState.ERROR
        self.metadata["last_error"] = error_msg
        self.metadata["error_at"] = time.time()

    # ── Privados ──

    def _truncate_history(self) -> None:
        """Trunca historial preservando system messages."""
        system_msgs = [m for m in self.messages if m.is_system]
        non_system = [m for m in self.messages if not m.is_system]
        # Mantener system messages + los ultimos mensajes
        keep_count = self.config.max_history_messages - len(system_msgs)
        if keep_count > 0:
            self.messages = system_msgs + non_system[-keep_count:]
        else:
            self.messages = system_msgs[:5] + non_system[-20:]
