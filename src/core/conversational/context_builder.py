"""
ContextBuilder del Asistente.

Construye el contexto completo para el pipeline y/o LLM,
combinando informacion de todas las fuentes disponibles:
  - System prompt (personalidad + instrucciones)
  - Historial de conversacion (mensajes recientes)
  - Memoria relevante (working, short-term, long-term)
  - Conocimiento (base de conocimiento)
  - Estado de conversacion (fase, topics)
  - Herramientas disponibles (specs para function calling)

Gestiona el budget de tokens para no exceder limites.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .types.base import PipelineContext
from .types.session import Session, Message, MessageRole
from .types.intent import AssistantIntent, IntentCategory
from .types.personality import PersonalityProfile
from .types.response import AssistantResponse
from ..config.constants import (  # type: ignore[import-unresolved]
    MAX_CONTEXT_TOKENS,
    CONTEXT_RESERVE_SYSTEM,
    CONTEXT_RESERVE_RESPONSE,
)
from .conversation import ConversationManager, ConversationState
from .memory import MemoryManager
from .knowledge import KnowledgeBase
from .tools import ToolManager

logger = logging.getLogger("zenic_agents.conversational.context_builder")


# ─── Config ───────────────────────────────────────────────────

@dataclass
class ContextBuilderConfig:
    """Configuracion del ContextBuilder."""
    max_context_tokens: int = MAX_CONTEXT_TOKENS
    system_reserve: int = CONTEXT_RESERVE_SYSTEM
    response_reserve: int = CONTEXT_RESERVE_RESPONSE
    max_history_messages: int = 20
    max_memory_entries: int = 5
    max_knowledge_entries: int = 3
    include_tools: bool = True
    include_conversation_state: bool = True


# ─── Resultado del builder ────────────────────────────────────

@dataclass
class BuiltContext:
    """Contexto construido listo para el pipeline/LLM."""
    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    knowledge_context: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    conversation_state: dict[str, Any] = field(default_factory=dict)
    total_tokens_estimated: int = 0
    build_time_ms: float = 0.0
    sources_used: list[str] = field(default_factory=list)

    @property
    def has_memory(self) -> bool:
        return len(self.memory_context) > 0

    @property
    def has_knowledge(self) -> bool:
        return len(self.knowledge_context) > 0

    @property
    def has_tools(self) -> bool:
        return len(self.tools) > 0

    def to_openai_messages(self) -> list[dict[str, Any]]:
        """Convierte a formato OpenAI chat completion messages."""
        msgs: list[dict[str, Any]] = []

        # System prompt
        if self.system_prompt:
            system_content = self.system_prompt
            # Inyectar memoria y conocimiento en system prompt
            if self.memory_context:
                mem_str = "\n".join(
                    f"- {m.get('content', '')}" for m in self.memory_context
                )
                system_content += f"\n\nMemoria relevante:\n{mem_str}"
            if self.knowledge_context:
                kno_str = "\n".join(
                    f"- {k.get('title', '')}: {k.get('content', '')[:200]}"
                    for k in self.knowledge_context
                )
                system_content += f"\n\nConocimiento relevante:\n{kno_str}"

            msgs.append({"role": "system", "content": system_content})

        # Historial de mensajes
        msgs.extend(self.messages)

        return msgs


# ─── ContextBuilder ───────────────────────────────────────────

class ContextBuilder:
    """
    Constructor de contexto para el pipeline.

    Combina todas las fuentes de informacion en un
    contexto coherente y dentro del budget de tokens.
    """

    def __init__(
        self,
        conversation_mgr: ConversationManager | None = None,
        memory_mgr: MemoryManager | None = None,
        knowledge_base: KnowledgeBase | None = None,
        tool_mgr: ToolManager | None = None,
        config: ContextBuilderConfig | None = None,
    ) -> None:
        self._conversation = conversation_mgr or ConversationManager()
        self._memory = memory_mgr or MemoryManager()
        self._knowledge = knowledge_base or KnowledgeBase()
        self._tools = tool_mgr or ToolManager()
        self._config = config or ContextBuilderConfig()

    def build(
        self,
        session: Session,
        intent: AssistantIntent,
        personality: PersonalityProfile | None = None,
        user_message: str = "",
    ) -> BuiltContext:
        """
        Construye el contexto completo.

        Pipeline: system → history → memory → knowledge →
                  tools → state → budget check.
        """
        start = time.time()
        sources: list[str] = []
        session_id = session.session_id

        # 1. System prompt
        system_prompt = self._build_system_prompt(personality, intent)
        sources.append("system_prompt")

        # 2. Historial de mensajes
        messages = self._build_history(session)
        sources.append("history")

        # 3. Memoria relevante
        memory_ctx = self._build_memory(session_id, user_message or intent.raw_text)
        if memory_ctx:
            sources.append("memory")

        # 4. Conocimiento
        knowledge_ctx = self._build_knowledge(intent, user_message)
        if knowledge_ctx:
            sources.append("knowledge")

        # 5. Herramientas
        tools = self._build_tools(intent) if self._config.include_tools else []
        if tools:
            sources.append("tools")

        # 6. Estado de conversacion
        conv_state = {}
        if self._config.include_conversation_state:
            conv_state = self._build_conversation_state(session_id)
            if conv_state:
                sources.append("conversation_state")

        # 7. Estimar tokens y truncar si es necesario
        total_tokens = self._estimate_tokens(
            system_prompt, messages, memory_ctx, knowledge_ctx
        )
        if total_tokens > self._config.max_context_tokens:
            messages = self._truncate_history(
                messages, total_tokens - self._config.max_context_tokens
            )

        elapsed = (time.time() - start) * 1000

        return BuiltContext(
            system_prompt=system_prompt,
            messages=messages,
            memory_context=memory_ctx,
            knowledge_context=knowledge_ctx,
            tools=tools,
            conversation_state=conv_state,
            total_tokens_estimated=self._estimate_tokens(
                system_prompt, messages, memory_ctx, knowledge_ctx
            ),
            build_time_ms=elapsed,
            sources_used=sources,
        )

    # ─── Componentes ───────────────────────────────────────────

    @staticmethod
    def _build_system_prompt(
        personality: PersonalityProfile | None,
        intent: AssistantIntent,
    ) -> str:
        """Construye el system prompt."""
        base = (
            "Eres Zenic-Agents Asistente, un asistente inteligente y versatil. "
            "Tu trabajo es ayudar al usuario de la mejor manera posible.\n\n"
        )

        # Personalidad
        if personality:
            base += personality.get_system_prompt_suffix() + "\n\n"

        # Ajuste por intencion
        if intent.is_code_related:
            base += (
                "El usuario esta trabajando en una tarea de codigo. "
                "Proporciona respuestas tecnicas precisas con ejemplos.\n"
            )
        elif intent.category == IntentCategory.QUESTION:
            base += (
                "El usuario esta haciendo una pregunta. "
                "Responde de forma clara y completa.\n"
            )

        return base

    def _build_history(self, session: Session) -> list[dict[str, Any]]:
        """Construye el historial de mensajes."""
        recent = session.get_recent_messages(self._config.max_history_messages)
        return [
            m.to_openai_format() for m in recent
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM)
        ]

    def _build_memory(
        self, session_id: str, query: str,
    ) -> list[dict[str, Any]]:
        """Busca memoria relevante."""
        if not query:
            return []
        result = self._memory.retrieve_for_context(
            query_text=query,
            session_id=session_id,
            max_results=self._config.max_memory_entries,
        )
        return result

    def _build_knowledge(
        self, intent: AssistantIntent, query: str,
    ) -> list[dict[str, Any]]:
        """Busca conocimiento relevante."""
        if not query:
            return []

        # Mapear intencion a categoria de conocimiento
        category_map: dict[IntentCategory, str] = {
            IntentCategory.CODE_CREATE: "programming",
            IntentCategory.CODE_DEBUG: "programming",
            IntentCategory.CODE_REFACTOR: "architecture",
            IntentCategory.CODE_OPTIMIZE: "programming",
            IntentCategory.QUESTION: "general",
        }
        category = category_map.get(intent.category, "general")

        result = self._knowledge.search(
            text=query,
            max_results=self._config.max_knowledge_entries,
            category=category,
        )

        return [e.to_context_dict() for e in result.entries]

    def _build_tools(self, intent: AssistantIntent) -> list[dict[str, Any]]:
        """Obtiene tools relevantes en formato OpenAI."""
        tools = self._tools.get_tools_for_intent(intent)
        return [t.to_openai_format() for t in tools]

    def _build_conversation_state(self, session_id: str) -> dict[str, Any]:
        """Obtiene estado de conversacion."""
        state = self._conversation.get_state(session_id)
        if state is None:
            return {}
        return state.to_context_dict()

    # ─── Token management ──────────────────────────────────────

    @staticmethod
    def _estimate_tokens(
        system: str,
        messages: list[dict[str, Any]],
        memory: list[dict[str, Any]],
        knowledge: list[dict[str, Any]],
    ) -> int:
        """Estima tokens (1 token ≈ 4 chars para espanol)."""
        total_chars = len(system)

        for msg in messages:
            total_chars += len(msg.get("content", ""))

        for mem in memory:
            total_chars += len(mem.get("content", ""))

        for kno in knowledge:
            total_chars += len(kno.get("content", "")) + len(kno.get("title", ""))

        return total_chars // 4  # Aproximacion

    def _truncate_history(
        self,
        messages: list[dict[str, Any]],
        excess_tokens: int,
    ) -> list[dict[str, Any]]:
        """Trunca el historial para reducir tokens."""
        # Eliminar mensajes mas antiguos (no system)
        chars_to_remove = excess_tokens * 4
        removed_chars = 0

        result: list[dict[str, Any]] = []
        for msg in reversed(messages):
            if removed_chars >= chars_to_remove:
                result.insert(0, msg)
            else:
                role = msg.get("role", "")
                if role == "system":
                    result.insert(0, msg)
                else:
                    removed_chars += len(msg.get("content", ""))

        return result
