"""
Tipos compartidos del Asistente (Fase 2).

Single source of truth para todas las dataclasses, enums,
protocols y tipos del modulo zenic_agents.conversational.

Fase 1: session, intent, response, personality, tool_use, base, memory, events
Fase 2: conversation state, knowledge types (added to existing)
"""

from .session import (
    SessionId,
    SessionState,
    Session,
    SessionConfig,
    Message,
    MessageRole,
    MessageMetadata,
)
from .intent import (
    AssistantIntent,
    IntentCategory,
    ConversationMode,
    IntentResult,
)
from .response import (
    AssistantResponse,
    ResponseFormat,
    ResponseMetadata,
    StreamingChunk,
)
from .personality import (
    PersonalityProfile,
    ToneLevel,
    LanguagePreference,
)
from .tool_use import (
    ToolCall,
    ToolResult,
    ToolPermission,
    ToolSpec,
)
from .base import (
    Result,
    Ok,
    Err,
    ok,
    err,
    PipelineContext,
    Priority,
    Severity,
    Processor,
    Classifier,
    Router,
    Generator,
    Store,
    Emitter,
    new_id,
)
from .memory import (
    MemoryEntry,
    MemoryType,
    MemoryCategory,
    MemoryQuery,
    MemoryResult,
    MemoryStats,
)
from .events import (
    Event,
    EventType,
    Subscription,
    EventHandler,
    AsyncEventHandler,
)

__all__ = [
    # Session
    "SessionId", "SessionState", "Session", "SessionConfig",
    "Message", "MessageRole", "MessageMetadata",
    # Intent
    "AssistantIntent", "IntentCategory", "ConversationMode", "IntentResult",
    # Response
    "AssistantResponse", "ResponseFormat", "ResponseMetadata", "StreamingChunk",
    # Personality
    "PersonalityProfile", "ToneLevel", "LanguagePreference",
    # Tool Use
    "ToolCall", "ToolResult", "ToolPermission", "ToolSpec",
    # Base (Fase 1)
    "Result", "Ok", "Err", "ok", "err",
    "PipelineContext", "Priority", "Severity",
    "Processor", "Classifier", "Router", "Generator", "Store", "Emitter",
    "new_id",
    # Memory (Fase 1)
    "MemoryEntry", "MemoryType", "MemoryCategory",
    "MemoryQuery", "MemoryResult", "MemoryStats",
    # Events (Fase 1)
    "Event", "EventType", "Subscription",
    "EventHandler", "AsyncEventHandler",
]
