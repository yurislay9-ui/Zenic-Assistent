"""
Motor de conversacion del asistente (Fase 2 — Capacidades).

Orquesta el flujo completo de procesamiento de un mensaje:

  Fase 1: Input -> Intent -> Route -> Process -> Memory -> Events
  Fase 2: Conversation -> Knowledge -> Context -> Tool exec
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, AsyncIterator, Optional

from .types.base import Result
from .types.session import Session
from .types.intent import AssistantIntent, IntentCategory
from .types.response import (
    AssistantResponse, ResponseFormat, ResponseMetadata, StreamingChunk,
)
from .types.personality import PersonalityProfile
from .types.memory import MemoryCategory
from .session_manager import SessionManager
from .personality_manager import PersonalityManager
from .zenic_bridge import ZenicBridge
from .engine_parts import IntentClassifier, ResponseGenerator, EngineFormatter
from .pipeline_handlers import PipelineHandlers
from .input import InputSanitizer, InputParser, InputEnricher
from .routing import AssistantRouter, PipelineSelector, FallbackChain
from .routing.router import Pipeline
from .routing.intent_engine import IntentEngine
from .routing.fallback_chain import FallbackEntry
from .memory import MemoryManager
from .tools import ToolManager
from .events import EventBus, EventTypes
from .conversation import ConversationManager
from .knowledge import KnowledgeBase
from .context_builder import ContextBuilder
from .engine_phase2_handlers import Phase2Handlers
from .engine_knowledge import load_builtin_knowledge

logger = logging.getLogger("zenic_agents.conversational.conversation")


class ConversationEngine:
    """
    Motor de conversacion principal (Fase 2).

    Pipeline: input -> intent -> route -> process ->
              memory -> conversation -> knowledge -> context -> events.
    """

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        personality_manager: Optional[PersonalityManager] = None,
        zenic_bridge: Optional[ZenicBridge] = None,
    ) -> None:
        # Core
        self._sessions = session_manager or SessionManager()
        self._personalities = personality_manager or PersonalityManager()
        self._bridge = zenic_bridge
        self._generator = ResponseGenerator()
        self._formatter = EngineFormatter()
        self._handlers = PipelineHandlers(
            generator=self._generator,
            formatter=self._formatter,
            personality_getter=self._personalities.get_default,
            bridge=self._bridge,
        )

        # Input + Intent + Routing (Fase 1)
        self._sanitizer = InputSanitizer()
        self._parser = InputParser()
        self._enricher = InputEnricher()
        self._intent_engine = IntentEngine()
        self._router = AssistantRouter(
            engine_available=self._bridge is not None and self._bridge.is_available,
        )
        self._pipeline_selector = PipelineSelector()
        self._fallback_chain = FallbackChain()

        # Fase 2 components
        self._memory = MemoryManager()
        self._tools = ToolManager()
        self._event_bus = EventBus()
        self._events = EventTypes(self._event_bus)
        self._conversation_mgr = ConversationManager()
        self._knowledge = KnowledgeBase()
        self._context_builder = ContextBuilder(
            conversation_mgr=self._conversation_mgr,
            memory_mgr=self._memory,
            knowledge_base=self._knowledge,
            tool_mgr=self._tools,
        )
        self._phase2_handlers = Phase2Handlers(self._tools)

        # Telemetria
        self._stats_lock = threading.Lock()
        self._total_requests = 0
        self._total_conversational = 0
        self._total_engine_calls = 0
        self._total_fallbacks = 0

        # Fallback garantizado
        self._fallback_chain.register(FallbackEntry(
            pipeline=Pipeline.CONVERSATIONAL,
            handler=PipelineHandlers.fallback_handler,
            priority=10,
            description="Fallback conversacional garantizado",
        ))

        # Cargar conocimiento base
        load_builtin_knowledge(self._knowledge)

    # ─── API Publica ──────────────────────────────────────────

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        personality: Optional[PersonalityProfile] = None,
    ) -> AssistantResponse:
        """Procesa un mensaje completo por el pipeline Fase 2."""
        start_time = time.time()
        self._increment_stat("total_requests")
        self._events.message_received(session_id=session_id, user_message=user_message)

        # 1. Sesion
        session = self._sessions.get_session(session_id)
        if session is None:
            return AssistantResponse.from_error("Sesion no encontrada.", source="error")

        # 2. Input pipeline
        sanitized_result = self._sanitizer.sanitize(user_message)
        if sanitized_result.is_err:
            return AssistantResponse.from_error(str(sanitized_result.error), source="sanitizer")
        sanitized = sanitized_result.unwrap
        parsed = self._parser.parse(sanitized.cleaned, sanitized.detected_language).unwrap

        # 3. Memory (unificado)
        memory_entries = self._memory.retrieve_for_context(
            query_text=sanitized.cleaned, session_id=session_id, max_results=5,
        )
        enriched = self._enricher.enrich(sanitized, parsed, session, memory_entries).unwrap
        self._sessions.add_user_message(session_id, user_message)

        # 4. Intent
        intent_result = self._intent_engine.classify(enriched, session)
        intent = intent_result.unwrap if intent_result.is_ok else self._classifier_fallback(user_message, session)

        # 5. Conversation (Fase 2)
        self._conversation_mgr.process_user_turn(
            session_id=session_id, content=user_message,
            intent=intent.category, confidence=intent.confidence,
            entities=[e.text for e in parsed.entities],
        )

        # 6. Events + Logging
        self._events.intent_classified(
            session_id=session_id, category=intent.category.value,
            confidence=intent.confidence, mode=intent.mode.value,
            is_conversational=intent.is_conversational, needs_engine=intent.needs_engine,
        )
        logger.info(f"Intent: {intent.category.value} (conf={intent.confidence:.2f})")

        # 7. Route
        route_result = self._router.route(intent)
        pipeline = route_result.unwrap.pipeline if route_result.is_ok else Pipeline.CONVERSATIONAL
        if route_result.is_ok and route_result.unwrap.fallback_used:
            self._increment_stat("total_fallbacks")

        # 8. Process
        response = await self._process_pipeline(pipeline, intent, enriched, session, personality)

        # 9. Post-process (Fase 2)
        self._conversation_mgr.process_assistant_turn(session_id, response.content, intent.category)
        self._store_memory(session_id, user_message, intent)
        self._memory.maybe_decay()

        # 10. Finalize
        elapsed = (time.time() - start_time) * 1000
        response.metadata.latency_ms = elapsed
        response.metadata.intent_category = intent.category.value
        self._sessions.add_assistant_message(session_id, response.content, metadata={
            "latency_ms": elapsed, "intent_category": intent.category.value,
            "source": response.metadata.source, "pipeline": pipeline.value,
        })
        self._events.response_generated(
            session_id=session_id, content_length=len(response.content),
            resp_source=response.metadata.source, latency_ms=elapsed,
        )
        return response

    async def stream_message(
        self, session_id: str, user_message: str,
        personality: Optional[PersonalityProfile] = None,
    ) -> AsyncIterator[StreamingChunk]:
        """Procesa un mensaje y retorna la respuesta como stream."""
        response = await self.process_message(session_id, user_message, personality)
        for i in range(0, len(response.content), 50):
            yield StreamingChunk.create(
                content=response.content[i:i + 50],
                is_final=(i + 50) >= len(response.content),
            )

    # ─── Public helpers ───────────────────────────────────────

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any], session_id: str = "") -> Result[Any, Exception]:
        """Ejecuta una herramienta."""
        return await self._tools.execute_tool(tool_name, arguments, session_id)

    def build_context(self, session_id: str, intent: AssistantIntent, personality: PersonalityProfile | None = None) -> dict[str, Any]:
        """Construye contexto completo para LLM/prompt."""
        session = self._sessions.get_session(session_id)
        if session is None:
            return {}
        ctx = self._context_builder.build(session=session, intent=intent, personality=personality, user_message=intent.raw_text)
        return {
            "system_prompt": ctx.system_prompt, "messages": ctx.to_openai_messages(),
            "tools": ctx.tools, "conversation_state": ctx.conversation_state,
            "sources_used": ctx.sources_used, "build_time_ms": ctx.build_time_ms,
        }

    def search_knowledge(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Busca en la base de conocimiento."""
        return [e.to_context_dict() for e in self._knowledge.search(query, max_results).entries]

    # ─── Pipeline ─────────────────────────────────────────────

    async def _process_pipeline(
        self, pipeline: Pipeline, intent: AssistantIntent,
        enriched: Any, session: Session, personality: Optional[PersonalityProfile],
    ) -> AssistantResponse:
        """Despacha al handler del pipeline."""
        if pipeline == Pipeline.CODE_ENGINE:
            self._increment_stat("total_engine_calls")
            return await self._handlers.handle_engine(enriched.text, intent, session, personality)
        elif pipeline == Pipeline.QUESTION_ANSWER:
            self._increment_stat("total_conversational")
            return self._handlers.handle_question(enriched, intent, session, personality)
        elif pipeline == Pipeline.COMMAND_HANDLER:
            return self._handlers.handle_command(enriched, session)
        elif pipeline == Pipeline.CONFIG_HANDLER:
            return self._handlers.handle_config(enriched, session)
        elif pipeline == Pipeline.TOOL_PIPELINE:
            return await self._phase2_handlers.handle_tool_pipeline(enriched, intent, session, personality)
        else:
            self._increment_stat("total_conversational")
            return self._handlers.handle_conversational(enriched.text, intent, session, personality)

    # ─── Memory ───────────────────────────────────────────────

    def _store_memory(self, session_id: str, message: str, intent: AssistantIntent) -> None:
        """Almacena en memoria via MemoryManager."""
        cat_map = {
            IntentCategory.CONFIG: MemoryCategory.PREFERENCE,
            IntentCategory.FEEDBACK: MemoryCategory.CORRECTION,
        }
        cat = cat_map.get(intent.category)
        if cat is None:
            cat = MemoryCategory.SKILL if intent.is_code_related else (
                MemoryCategory.FACT if intent.category == IntentCategory.QUESTION
                else MemoryCategory.CONTEXT
            )
        result = self._memory.store(content=message[:500], category=cat, session_id=session_id, source="user", tags=[intent.category.value])
        if result.is_ok:
            self._events.memory_stored(session_id=session_id, category=cat.value, importance=result.unwrap.importance)

    # ─── Helpers ──────────────────────────────────────────────

    def _classifier_fallback(self, message: str, session: Session) -> AssistantIntent:
        """Fallback al clasificador simple si IntentEngine falla."""
        from .engine_parts import IntentClassifier
        return IntentClassifier().classify(message, session)

    def _increment_stat(self, name: str) -> None:
        with self._stats_lock:
            setattr(self, f"_{name}", getattr(self, f"_{name}", 0) + 1)

    # ─── Properties ───────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        with self._stats_lock:
            return {
                "total_requests": self._total_requests,
                "total_conversational": self._total_conversational,
                "total_engine_calls": self._total_engine_calls,
                "total_fallbacks": self._total_fallbacks,
                "sessions": self._sessions.stats,
                "router": self._router.stats,
                "memory": self._memory.stats,
                "tools": self._tools.stats,
                "events": self._event_bus.stats,
                "conversation": self._conversation_mgr.stats,
                "knowledge": self._knowledge.stats,
            }

    @property
    def event_bus(self) -> EventBus: return self._event_bus
    @property
    def memory_manager(self) -> MemoryManager: return self._memory
    @property
    def tool_manager(self) -> ToolManager: return self._tools
    @property
    def conversation_manager(self) -> ConversationManager: return self._conversation_mgr
    @property
    def knowledge_base(self) -> KnowledgeBase: return self._knowledge
    @property
    def router(self) -> AssistantRouter: return self._router
