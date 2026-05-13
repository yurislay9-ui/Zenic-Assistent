"""
ConversationManager del Asistente.

Orquesta las sesiones de conversacion, integrando
el tracking de turnos, la sumarizacion de contexto
y el manejo del estado de la conversacion.

Responsabilidades:
  - Gestionar estados de conversacion por sesion
  - Coordinar turn tracking y topic detection
  - Disparar sumarizacion cuando el contexto crece
  - Proveer contexto enriquecido para el pipeline
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from ...types.base import Result, Ok
from ...types.session import Session, Message, MessageRole
from ...types.intent import IntentCategory, ConversationMode
from ...types.memory import MemoryEntry, MemoryQuery, MemoryCategory
from .state import ConversationState, ConversationPhase, ConversationTopic
from .turn_tracker import TurnTracker
from .summarizer import ContextSummarizer, SummarizerConfig

logger = logging.getLogger("zenic_agents.conversational.conversation.manager")


class ConversationManager:
    """
    Gestiona conversaciones multi-turno.

    Integra TurnTracker, ContextSummarizer y ConversationState
    para mantener conversaciones coherentes y contextualizadas.
    Thread-safe.
    """

    def __init__(
        self,
        summarizer_config: SummarizerConfig | None = None,
    ) -> None:
        self._states: dict[str, ConversationState] = {}
        self._trackers: dict[str, TurnTracker] = {}
        self._summarizer = ContextSummarizer(summarizer_config)
        self._lock = threading.RLock()
        self._stats = {
            "conversations_started": 0,
            "conversations_ended": 0,
            "total_turns": 0,
            "topic_shifts": 0,
            "summaries_generated": 0,
        }

    # ─── Lifecycle ─────────────────────────────────────────────

    def start_conversation(
        self,
        session_id: str,
        mode: ConversationMode = ConversationMode.NORMAL,
    ) -> ConversationState:
        """Inicia una nueva conversacion para una sesion."""
        with self._lock:
            state = ConversationState(
                session_id=session_id,
                phase=ConversationPhase.GREETING,
                mode=mode,
            )
            self._states[session_id] = state
            self._trackers[session_id] = TurnTracker()
            self._stats["conversations_started"] += 1

            logger.info(f"Conversacion iniciada: {session_id[:8]}...")
            return state

    def end_conversation(self, session_id: str) -> bool:
        """Termina una conversacion."""
        with self._lock:
            state = self._states.get(session_id)
            if state is None:
                return False

            state.update_phase(ConversationPhase.CLOSING)
            self._stats["conversations_ended"] += 1
            logger.info(f"Conversacion terminada: {session_id[:8]}...")
            return True

    # ─── Estado ────────────────────────────────────────────────

    def get_state(self, session_id: str) -> ConversationState | None:
        """Obtiene el estado de conversacion de una sesion."""
        return self._states.get(session_id)

    def get_or_create(
        self,
        session_id: str,
        mode: ConversationMode = ConversationMode.NORMAL,
    ) -> ConversationState:
        """Obtiene o crea el estado de conversacion."""
        state = self._states.get(session_id)
        if state is None:
            return self.start_conversation(session_id, mode)
        return state

    # ─── Procesamiento de turnos ───────────────────────────────

    def process_user_turn(
        self,
        session_id: str,
        content: str,
        intent: IntentCategory = IntentCategory.UNKNOWN,
        confidence: float = 0.0,
        entities: list[str] | None = None,
    ) -> Result[ConversationState]:
        """
        Procesa un turno del usuario.

        Actualiza estado, registra turno, detecta topics
        y ajusta la fase de la conversacion.
        """
        with self._lock:
            state = self._states.get(session_id)
            tracker = self._trackers.get(session_id)

            if state is None or tracker is None:
                return Ok(self.start_conversation(session_id))

            # 1. Detectar topic
            topic_name = self._infer_topic(content, intent, state)

            # 2. Registrar turno
            turn = tracker.record_turn(
                role="user",
                content=content,
                intent=intent,
                confidence=confidence,
                topic=topic_name,
                entities=entities,
            )

            # 3. Actualizar estado
            state.advance_turn(intent, confidence)

            # 4. Actualizar topics
            self._update_topics(state, topic_name, intent, content)

            # 5. Ajustar fase
            phase = tracker.infer_phase()
            state.update_phase(phase)

            # 6. Ajustar modo
            state.mode = self._infer_mode(intent, content)

            # 7. Stats
            self._stats["total_turns"] += 1
            if turn.is_topic_shift:
                self._stats["topic_shifts"] += 1

            return Ok(state)

    def process_assistant_turn(
        self,
        session_id: str,
        content: str,
        intent: IntentCategory = IntentCategory.UNKNOWN,
    ) -> None:
        """Registra un turno del asistente."""
        tracker = self._trackers.get(session_id)
        if tracker:
            tracker.record_turn(
                role="assistant",
                content=content,
                intent=intent,
            )

    # ─── Contexto ──────────────────────────────────────────────

    def get_context_for_pipeline(
        self,
        session: Session,
    ) -> dict[str, Any]:
        """
        Obtiene contexto enriquecido para el pipeline.

        Incluye: estado de conversacion, resumen de contexto,
        coherencia, topics activos y sugerencias.
        """
        session_id = session.session_id
        state = self._states.get(session_id)
        tracker = self._trackers.get(session_id)

        # Sumarizar si es necesario
        summary = self._summarizer.summarize(session)
        if summary.messages_summarized > 0:
            self._stats["summaries_generated"] += 1
            if state:
                state.context_summary = summary.summary_text

        context: dict[str, Any] = {
            "conversation_phase": ConversationPhase.GREETING.value,
            "conversation_mode": ConversationMode.NORMAL.value,
            "turn_count": 0,
            "active_topics": [],
            "coherence": 1.0,
            "has_clarifications": False,
            "context_summary": summary.summary_text if summary.has_summary else "",
        }

        if state:
            context.update({
                "conversation_phase": state.phase.value,
                "conversation_mode": state.mode.value,
                "turn_count": state.turn_count,
                "active_topics": [t.name for t in state.active_topics],
                "has_clarifications": state.has_pending_clarifications,
            })

        if tracker:
            context["coherence"] = tracker.compute_coherence()

        return context

    def should_summarize(self, session: Session) -> bool:
        """Verifica si la sesion necesita sumarizacion."""
        config = self._summarizer._config
        return len(session.messages) >= config.min_messages_to_summarize

    # ─── Privados ──────────────────────────────────────────────

    @staticmethod
    def _infer_topic(
        content: str, intent: IntentCategory, state: ConversationState,
    ) -> str:
        """Infiere el topic del mensaje."""
        text_lower = content.lower()

        # Buscar topic existente que matchee
        for topic in state.active_topics:
            # Match por keywords del topic en el contenido
            topic_words = set(topic.name.lower().split())
            content_words = set(text_lower.split()[:20])
            overlap = len(topic_words & content_words)
            if overlap > 0 and overlap / max(len(topic_words), 1) > 0.3:
                return topic.name

        # Crear nuevo topic basado en intencion
        topic_map: dict[IntentCategory, str] = {
            IntentCategory.CODE_CREATE: "code_generation",
            IntentCategory.CODE_DEBUG: "debugging",
            IntentCategory.CODE_REFACTOR: "refactoring",
            IntentCategory.CODE_OPTIMIZE: "optimization",
            IntentCategory.CODE_ANALYZE: "code_analysis",
            IntentCategory.CODE_EXPLAIN: "code_explanation",
            IntentCategory.QUESTION: "general_questions",
            IntentCategory.CONFIG: "configuration",
            IntentCategory.AUTOMATION: "automation",
            IntentCategory.BUSINESS: "business_logic",
            IntentCategory.CHAT: "general_chat",
            IntentCategory.FEEDBACK: "feedback",
        }

        return topic_map.get(intent, "general")

    @staticmethod
    def _update_topics(
        state: ConversationState,
        topic_name: str,
        intent: IntentCategory,
        content: str,
    ) -> None:
        """Actualiza los topics de la conversacion."""
        existing = state.find_topic(topic_name)
        if existing:
            existing.touch()
        else:
            new_topic = ConversationTopic(
                name=topic_name,
                category=intent,
            )
            state.add_topic(new_topic)

        # Limpiar topics inactivos (mas de 10 min sin mencion)
        cutoff = 600.0  # 10 minutos
        stale = [
            t for t in state.active_topics
            if (state.last_activity - t.last_mentioned) > cutoff
        ]
        for t in stale:
            state.complete_topic(t.name)

    @staticmethod
    def _infer_mode(intent: IntentCategory, content: str) -> ConversationMode:
        """Infiere el modo de conversacion."""
        if intent in (
            IntentCategory.CODE_CREATE, IntentCategory.CODE_DEBUG,
            IntentCategory.CODE_REFACTOR, IntentCategory.CODE_OPTIMIZE,
        ):
            return ConversationMode.CODING

        if intent == IntentCategory.QUESTION:
            step_words = ["paso a paso", "step by step", "explica", "explain"]
            if any(w in content.lower() for w in step_words):
                return ConversationMode.TEACHING
            return ConversationMode.REASONING

        if intent == IntentCategory.AUTOMATION:
            return ConversationMode.AUTOMATION

        return ConversationMode.NORMAL

    # ─── Stats ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del conversation manager."""
        with self._lock:
            return {
                **self._stats,
                "active_conversations": len(self._states),
            }
