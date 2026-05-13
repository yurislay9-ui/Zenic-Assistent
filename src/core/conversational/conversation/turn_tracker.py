"""
Tracker de turnos de conversacion.

Rastrea los turnos de la conversacion, detecta
cambios de topic, referencias cruzadas y patrones
de comportamiento del usuario.

Thread-safe y determinista.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from ...types.intent import IntentCategory
from .state import ConversationState, ConversationTopic, ConversationPhase


# ─── Turno registrado ─────────────────────────────────────────

@dataclass
class TurnRecord:
    """Registro de un turno de conversacion."""
    turn_number: int = 0
    role: str = "user"          # user, assistant, system
    content: str = ""
    intent: IntentCategory = IntentCategory.UNKNOWN
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    topic: str = ""
    is_topic_shift: bool = False
    entities: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    @property
    def is_user(self) -> bool:
        return self.role == "user"

    @property
    def is_assistant(self) -> bool:
        return self.role == "assistant"


# ─── Deteccion de topic shift ─────────────────────────────────

_SHIFT_INDICATORS_ES: list[str] = [
    "ahora", "cambiando de tema", "por otro lado",
    "tambien necesito", "otra cosa", "hablando de",
    "volviendo a", "antes decias", "y sobre",
]

_SHIFT_INDICATORS_EN: list[str] = [
    "now", "changing topic", "on another note",
    "also need", "another thing", "speaking of",
    "going back to", "you mentioned earlier", "what about",
]

_REFERENCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(eso|aquello|eso que dijiste|lo anterior|lo de antes)\b", re.I),
    re.compile(r"\b(that|the above|what you said|earlier|previously)\b", re.I),
    re.compile(r"\b(el ultimo|la ultima|el anterior|el previo)\b", re.I),
    re.compile(r"\b(the last|the previous|the one before)\b", re.I),
]


class TurnTracker:
    """
    Tracker de turnos de conversacion.

    Registra cada turno, detecta topic shifts,
    identifica referencias cruzadas y calcula
    la coherencia tematica de la conversacion.
    """

    def __init__(self, max_history: int = 100) -> None:
        self._turns: list[TurnRecord] = []
        self._max_history = max_history
        self._topic_shift_count = 0
        self._reference_count = 0

    # ─── Registro ──────────────────────────────────────────────

    def record_turn(
        self,
        role: str,
        content: str,
        intent: IntentCategory = IntentCategory.UNKNOWN,
        confidence: float = 0.0,
        topic: str = "",
        entities: list[str] | None = None,
    ) -> TurnRecord:
        """
        Registra un turno y retorna el registro.

        Detecta topic shifts y referencias cruzadas.
        """
        turn_number = len(self._turns) + 1

        # Detectar topic shift
        is_shift = self._detect_topic_shift(content, intent, turn_number)
        if is_shift:
            self._topic_shift_count += 1

        # Detectar referencias cruzadas
        refs = self._detect_references(content)

        turn = TurnRecord(
            turn_number=turn_number,
            role=role,
            content=content[:500],  # Truncar para memoria
            intent=intent,
            confidence=confidence,
            topic=topic,
            is_topic_shift=is_shift,
            entities=entities or [],
            references=refs,
        )

        self._turns.append(turn)
        self._reference_count += len(refs)

        # Truncar historial
        if len(self._turns) > self._max_history:
            self._turns = self._turns[-self._max_history:]

        return turn

    # ─── Consulta ──────────────────────────────────────────────

    def get_recent(self, count: int = 10) -> list[TurnRecord]:
        """Obtiene los ultimos N turnos."""
        return self._turns[-count:]

    def get_user_turns(self, count: int = 10) -> list[TurnRecord]:
        """Filtra solo turnos del usuario."""
        user_turns = [t for t in self._turns if t.is_user]
        return user_turns[-count:]

    def get_by_topic(self, topic: str) -> list[TurnRecord]:
        """Filtra turnos por topic."""
        return [t for t in self._turns if t.topic == topic]

    def get_topic_shifts(self) -> list[TurnRecord]:
        """Retorna todos los topic shifts detectados."""
        return [t for t in self._turns if t.is_topic_shift]

    def find_referencing_turns(self, turn_number: int) -> list[TurnRecord]:
        """Busca turnos que referencian a un turno especifico."""
        return [
            t for t in self._turns
            if str(turn_number) in t.references
        ]

    def compute_coherence(self, window: int = 5) -> float:
        """
        Computa la coherencia tematica reciente.

        Retorna 0.0-1.0 indicando cuan coherente es
        la conversacion en los ultimos N turnos.
        """
        recent = self._turns[-window:]
        if len(recent) < 2:
            return 1.0

        shifts = sum(1 for t in recent if t.is_topic_shift)
        max_shifts = len(recent)

        # Menos shifts = mas coherente
        coherence = 1.0 - (shifts / max_shifts)
        return max(0.0, min(1.0, coherence))

    def infer_phase(self) -> ConversationPhase:
        """Infiere la fase actual basada en los turnos."""
        if not self._turns:
            return ConversationPhase.GREETING

        recent = self._turns[-3:]
        recent_intents = [t.intent for t in recent]

        # Si los ultimos 3 turnos son CHAT o saludos
        if all(i == IntentCategory.CHAT for i in recent_intents):
            if len(self._turns) <= 2:
                return ConversationPhase.GREETING
            return ConversationPhase.EXPLORING

        # Si hay turnos de codigo o trabajo
        working_cats = {
            IntentCategory.CODE_CREATE, IntentCategory.CODE_DEBUG,
            IntentCategory.CODE_REFACTOR, IntentCategory.CODE_OPTIMIZE,
            IntentCategory.AUTOMATION, IntentCategory.BUSINESS,
        }
        if any(i in working_cats for i in recent_intents):
            return ConversationPhase.WORKING

        # Si hay preguntas
        if IntentCategory.QUESTION in recent_intents:
            return ConversationPhase.EXPLORING

        # Si hay comandos de config
        if IntentCategory.CONFIG in recent_intents:
            return ConversationPhase.WORKING

        # Feedback = seguimiento
        if IntentCategory.FEEDBACK in recent_intents:
            return ConversationPhase.FOLLOW_UP

        return ConversationPhase.EXPLORING

    # ─── Stats ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Estadisticas del tracker."""
        return {
            "total_turns": len(self._turns),
            "topic_shifts": self._topic_shift_count,
            "references_found": self._reference_count,
            "coherence": self.compute_coherence(),
            "user_turns": sum(1 for t in self._turns if t.is_user),
            "assistant_turns": sum(1 for t in self._turns if t.is_assistant),
        }

    # ─── Privados ──────────────────────────────────────────────

    def _detect_topic_shift(
        self,
        content: str,
        intent: IntentCategory,
        turn_number: int,
    ) -> bool:
        """Detecta si hay un cambio de topic."""
        # Primeros turnos no son shifts
        if turn_number <= 1:
            return False

        text_lower = content.lower()

        # Indicadores linguisticos de shift
        for indicator in _SHIFT_INDICATORS_ES + _SHIFT_INDICATORS_EN:
            if indicator in text_lower:
                return True

        # Shift de categoria de intencion
        if self._turns:
            last_intent = self._turns[-1].intent
            if (
                intent != last_intent
                and intent != IntentCategory.UNKNOWN
                and last_intent != IntentCategory.UNKNOWN
            ):
                # Solo es shift si las categorias son muy diferentes
                if intent.is_conversational != last_intent.is_conversational:
                    return True

        return False

    @staticmethod
    def _detect_references(content: str) -> list[str]:
        """Detecta referencias cruzadas en el contenido."""
        refs: list[str] = []
        for pattern in _REFERENCE_PATTERNS:
            if pattern.search(content):
                refs.append(pattern.pattern)
        return refs
