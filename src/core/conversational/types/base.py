"""
Tipos base del Asistente.

Protocolos, generics y abstracciones fundamentales que
definen los contratos del sistema. Todo componente
concreto implementa estos protocolos.

Principios:
  - Protocol-based DI (inyeccion por protocolo, no por clase)
  - Result monad para manejo explicito de errores
  - Composable via estos contratos
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Generic,
    Protocol,
    TypeVar,
    runtime_checkable,
)


# ─── Result Monad ─────────────────────────────────────────────

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


@dataclass
class Ok(Generic[T]):
    """Resultado exitoso."""
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False

    @property
    def unwrap(self) -> T:
        return self.value


@dataclass
class Err(Generic[E]):
    """Resultado con error."""
    error: E

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True

    def unwrap(self) -> Any:
        raise self.error


Result = Ok[T] | Err[E]


def ok(value: T) -> Ok[T]:
    """Factory para Ok."""
    return Ok(value=value)


def err(error: E) -> Err[E]:
    """Factory para Err."""
    return Err(error=error)


# ─── Identificadores tipados ─────────────────────────────────

SessionId = str
MessageId = str
ToolCallId = str
EventId = str
MemoryId = str


def new_id(prefix: str = "") -> str:
    """Genera un ID unico con prefijo opcional."""
    uid = uuid.uuid4().hex[:12]
    ts = str(int(time.time() * 1000))[-8:]
    return f"{prefix}_{uid}_{ts}" if prefix else f"{uid}_{ts}"


# ─── Prioridad y Severidad ───────────────────────────────────

class Priority(str, Enum):
    """Prioridad de procesamiento."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Severity(str, Enum):
    """Severidad de un evento o error."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


# ─── Protocolos Core ─────────────────────────────────────────

@runtime_checkable
class Processor(Protocol):
    """Protocolo base para cualquier procesador del pipeline."""

    async def process(self, data: Any) -> Result[Any, Exception]:
        """Procesa datos y retorna Result."""
        ...


@runtime_checkable
class Classifier(Protocol):
    """Protocolo para clasificadores (intencion, categoria, etc)."""

    def classify(self, text: str, context: dict[str, Any] | None = None) -> Result[Any, Exception]:
        """Clasifica texto con contexto opcional."""
        ...


@runtime_checkable
class Router(Protocol):
    """Protocolo para routers (seleccion de pipeline)."""

    def route(self, intent: Any, context: dict[str, Any]) -> Result[str, Exception]:
        """Rutea basado en intencion y contexto."""
        ...


@runtime_checkable
class Generator(Protocol):
    """Protocolo para generadores de respuesta."""

    async def generate(self, prompt: str, context: dict[str, Any]) -> Result[Any, Exception]:
        """Genera respuesta basada en prompt y contexto."""
        ...


@runtime_checkable
class Store(Protocol):
    """Protocolo para almacenamiento (memoria, cache, etc)."""

    async def store(self, key: str, value: Any, ttl: float | None = None) -> Result[bool, Exception]:
        """Almacena un valor con TTL opcional."""
        ...

    async def retrieve(self, key: str) -> Result[Any, Exception]:
        """Recupera un valor por clave."""
        ...

    async def delete(self, key: str) -> Result[bool, Exception]:
        """Elimina un valor por clave."""
        ...


@runtime_checkable
class Emitter(Protocol):
    """Protocolo para emisores de eventos."""

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emite un evento."""
        ...


# ─── Pipeline Context ────────────────────────────────────────

@dataclass
class PipelineContext:
    """
    Contexto que fluye por todo el pipeline.

    Se enriquece en cada etapa: input → intent → router → response.
    Inmutable en su estructura, mutable en sus datos.
    """
    session_id: SessionId = ""
    message_id: MessageId = field(default_factory=lambda: new_id("msg"))
    user_message: str = ""
    normalized_message: str = ""
    intent: Any | None = None
    route: str = ""
    personality: Any | None = None
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    priority: Priority = Priority.NORMAL

    @property
    def elapsed_ms(self) -> float:
        """Milisegundos transcurridos desde la creacion."""
        return (time.time() - self.start_time) * 1000

    def with_field(self, **kwargs: Any) -> PipelineContext:
        """Crea una copia con campos actualizados."""
        data = {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "user_message": self.user_message,
            "normalized_message": self.normalized_message,
            "intent": self.intent,
            "route": self.route,
            "personality": self.personality,
            "memory_context": self.memory_context,
            "tool_results": self.tool_results,
            "metadata": self.metadata,
            "start_time": self.start_time,
            "priority": self.priority,
        }
        data.update(kwargs)
        return PipelineContext(**data)


# ─── Callbacks ────────────────────────────────────────────────

AsyncCallback = Callable[..., Any]
StreamCallback = Callable[[str], None]
ErrorCallback = Callable[[Exception], None]
