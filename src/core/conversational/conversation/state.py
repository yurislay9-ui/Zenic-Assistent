"""
Estado de conversacion del Asistente.

Modela el estado completo de una conversacion activa:
fase, topics, intenciones previas, referencias
 cruzadas y metadata de telemetria.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..types.base import new_id
from ..types.intent import IntentCategory, ConversationMode


# ─── Fase de la conversacion ──────────────────────────────────

class ConversationPhase(str, Enum):
    """Fases de una conversacion."""
    GREETING = "greeting"           # Inicio, saludo
    EXPLORING = "exploring"         # El usuario esta explorando
    WORKING = "working"             # Trabajo activo en una tarea
    CLARIFYING = "clarifying"       # Pidiendo aclaraciones
    DELIVERING = "delivering"       # Entregando resultados
    FOLLOW_UP = "follow_up"        # Seguimiento post-entrega
    CLOSING = "closing"            # Despedida o fin
    IDLE = "idle"                  # Sin actividad


# ─── Topic de conversacion ────────────────────────────────────

@dataclass
class ConversationTopic:
    """Topic activo en la conversacion."""
    name: str = ""
    category: IntentCategory = IntentCategory.UNKNOWN
    started_at: float = field(default_factory=time.time)
    last_mentioned: float = field(default_factory=time.time)
    mention_count: int = 1
    related_entities: list[str] = field(default_factory=list)
    confidence: float = 0.5

    @property
    def age_seconds(self) -> float:
        return time.time() - self.started_at

    def touch(self) -> None:
        """Actualiza el timestamp de ultima mencion."""
        self.last_mentioned = time.time()
        self.mention_count += 1


# ─── Estado de conversacion ───────────────────────────────────

@dataclass
class ConversationState:
    """
    Estado completo de una conversacion.

    Rastrea la fase, topics activos, intenciones previas,
    modo de conversacion y metadata de telemetria.
    """
    state_id: str = field(default_factory=lambda: new_id("conv"))
    session_id: str = ""
    phase: ConversationPhase = ConversationPhase.GREETING
    mode: ConversationMode = ConversationMode.NORMAL

    # Topics
    active_topics: list[ConversationTopic] = field(default_factory=list)
    completed_topics: list[ConversationTopic] = field(default_factory=list)

    # Intenciones
    intent_history: list[IntentCategory] = field(default_factory=list)
    last_intent: IntentCategory = IntentCategory.UNKNOWN
    last_confidence: float = 0.0

    # Referencias
    pending_clarifications: list[str] = field(default_factory=list)
    unresolved_references: list[str] = field(default_factory=list)

    # Contexto
    context_summary: str = ""
    turn_count: int = 0
    total_tokens_used: int = 0

    # Metadata
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Propiedades ──

    @property
    def current_topic(self) -> ConversationTopic | None:
        """Topic mas reciente."""
        if not self.active_topics:
            return None
        return max(self.active_topics, key=lambda t: t.last_mentioned)

    @property
    def is_active(self) -> bool:
        """La conversacion esta activa."""
        return self.phase not in (ConversationPhase.CLOSING, ConversationPhase.IDLE)

    @property
    def has_pending_clarifications(self) -> bool:
        return len(self.pending_clarifications) > 0

    @property
    def topic_count(self) -> int:
        return len(self.active_topics)

    # ── Metodos ──

    def advance_turn(self, intent: IntentCategory, confidence: float = 0.0) -> None:
        """Avanza un turno de conversacion."""
        self.turn_count += 1
        self.last_intent = intent
        self.last_confidence = confidence
        self.intent_history.append(intent)
        self.last_activity = time.time()
        # Mantener solo ultimas 50 intenciones
        if len(self.intent_history) > 50:
            self.intent_history = self.intent_history[-50:]

    def add_topic(self, topic: ConversationTopic) -> None:
        """Agrega un topic activo."""
        self.active_topics.append(topic)

    def complete_topic(self, topic_name: str) -> None:
        """Mueve un topic a completados."""
        for i, t in enumerate(self.active_topics):
            if t.name == topic_name:
                self.completed_topics.append(self.active_topics.pop(i))
                return

    def find_topic(self, name: str) -> ConversationTopic | None:
        """Busca un topic por nombre."""
        for t in self.active_topics:
            if t.name == name:
                return t
        return None

    def update_phase(self, phase: ConversationPhase) -> None:
        """Actualiza la fase de la conversacion."""
        old_phase = self.phase
        self.phase = phase
        self.metadata["phase_transition"] = {
            "from": old_phase.value,
            "to": phase.value,
            "at": time.time(),
        }

    def add_clarification(self, question: str) -> None:
        """Agrega una aclaracion pendiente."""
        self.pending_clarifications.append(question)

    def resolve_clarification(self, index: int = 0) -> str | None:
        """Resuelve una aclaracion pendiente."""
        if not self.pending_clarifications:
            return None
        if index >= len(self.pending_clarifications):
            return None
        return self.pending_clarifications.pop(index)

    def to_context_dict(self) -> dict[str, Any]:
        """Exporta el estado como diccionario para contexto."""
        return {
            "phase": self.phase.value,
            "mode": self.mode.value,
            "turn_count": self.turn_count,
            "last_intent": self.last_intent.value,
            "active_topics": [
                {"name": t.name, "category": t.category.value, "mentions": t.mention_count}
                for t in self.active_topics
            ],
            "has_clarifications": self.has_pending_clarifications,
            "context_summary": self.context_summary[:500] if self.context_summary else "",
        }
