"""
Sumarizador de contexto de conversacion.

Resume conversaciones largas para mantener la ventana
de contexto dentro de limites, preservando la informacion
mas relevante.

Estrategias:
  - Sliding window: Mantiene ultimos N mensajes completos
  - Compression: Resume mensajes antiguos en un parrafo
  - Importance-based: Prioriza mensajes por importancia
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..types.session import Session, Message, MessageRole
from ..types.intent import IntentCategory
from .turn_tracker import TurnRecord

logger = logging.getLogger("zenic_agents.conversational.summarizer")


# ─── Config del sumarizador ───────────────────────────────────

@dataclass
class SummarizerConfig:
    """Configuracion del sumarizador de contexto."""
    max_full_messages: int = 10       # Mensajes completos recientes
    max_summary_length: int = 500     # Caracteres max del resumen
    min_messages_to_summarize: int = 6  # Min mensajes antes de resumir
    preserve_system_messages: bool = True
    preserve_code_blocks: bool = True


# ─── Resultado del resumen ────────────────────────────────────

@dataclass
class ContextSummary:
    """Resultado del proceso de sumarizacion."""
    full_messages: list[Message] = field(default_factory=list)
    summary_text: str = ""
    messages_summarized: int = 0
    messages_kept: int = 0
    compression_ratio: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def has_summary(self) -> bool:
        return len(self.summary_text) > 0

    def to_context_string(self) -> str:
        """Convierte a string para inyectar en prompt."""
        parts: list[str] = []

        if self.summary_text:
            parts.append(f"[Resumen de conversacion previa]:\n{self.summary_text}")

        for msg in self.full_messages:
            role = msg.role.value
            content = msg.content[:300]  # Truncar mensajes largos
            parts.append(f"[{role}]: {content}")

        return "\n".join(parts)


# ─── Sumarizador ──────────────────────────────────────────────

class ContextSummarizer:
    """
    Sumarizador de contexto de conversacion.

    Reduce la ventana de contexto cuando la conversacion
    crece, manteniendo la informacion mas relevante.
    """

    def __init__(self, config: SummarizerConfig | None = None) -> None:
        self._config = config or SummarizerConfig()

    def summarize(self, session: Session) -> ContextSummary:
        """
        Sumariza la sesion si excede el limite.

        Estrategia:
          1. Separar system messages
          2. Mantener ultimos N mensajes completos
          3. Comprimir los anteriores en un resumen
          4. Calcular ratio de compresion
        """
        messages = session.messages

        # No resumir si hay pocos mensajes
        if len(messages) <= self._config.min_messages_to_summarize:
            return ContextSummary(
                full_messages=messages,
                messages_kept=len(messages),
            )

        # Separar system messages
        system_msgs = [m for m in messages if m.is_system]
        non_system = [m for m in messages if not m.is_system]

        # Mensajes a mantener completos
        keep_count = self._config.max_full_messages
        to_keep = non_system[-keep_count:]
        to_summarize = non_system[:-keep_count]

        # Generar resumen de los mensajes antiguos
        summary_text = self._generate_summary(to_summarize)

        # Calcular compresion
        original_chars = sum(len(m.content) for m in to_summarize)
        summary_chars = len(summary_text)
        compression = (
            1.0 - (summary_chars / max(original_chars, 1))
            if original_chars > 0 else 0.0
        )

        # Componer mensajes finales
        final_messages: list[Message] = []
        if self._config.preserve_system_messages:
            final_messages.extend(system_msgs)

        # Agregar resumen como mensaje de sistema si existe
        if summary_text:
            summary_msg = Message(
                role=MessageRole.SYSTEM,
                content=f"[Resumen de conversacion previa]:\n{summary_text}",
            )
            final_messages.append(summary_msg)

        final_messages.extend(to_keep)

        return ContextSummary(
            full_messages=final_messages,
            summary_text=summary_text,
            messages_summarized=len(to_summarize),
            messages_kept=len(to_keep) + len(system_msgs),
            compression_ratio=compression,
        )

    def summarize_turns(self, turns: list[TurnRecord]) -> str:
        """Sumariza una lista de turnos en texto."""
        if not turns:
            return ""

        # Agrupar por topic
        topic_groups: dict[str, list[TurnRecord]] = {}
        for turn in turns:
            topic = turn.topic or "general"
            if topic not in topic_groups:
                topic_groups[topic] = []
            topic_groups[topic].append(turn)

        # Generar resumen por topic
        parts: list[str] = []
        for topic, topic_turns in topic_groups.items():
            user_msgs = [t for t in topic_turns if t.is_user]
            asst_msgs = [t for t in topic_turns if t.is_assistant]

            # Extraer intenciones dominantes
            intents = [t.intent.value for t in user_msgs if t.intent != IntentCategory.UNKNOWN]
            dominant = max(set(intents), key=intents.count) if intents else "chat"

            parts.append(
                f"- Topic '{topic}' ({len(user_msgs)} msgs, intent: {dominant}): "
                f"{' '.join(t.content[:80] for t in user_msgs[:3])}"
            )

        return "\n".join(parts[:10])  # Max 10 topics

    # ─── Privados ──────────────────────────────────────────────

    def _generate_summary(self, messages: list[Message]) -> str:
        """
        Genera un resumen extractivo de los mensajes.

        Usa extractive summarization: selecciona las oraciones
        mas importantes basado en posicion, longitud y contenido.
        """
        if not messages:
            return ""

        # Extraer oraciones con scores
        scored_sentences: list[tuple[str, float]] = []

        for i, msg in enumerate(messages):
            if msg.is_system:
                continue

            sentences = self._split_sentences(msg.content)
            for j, sentence in enumerate(sentences):
                score = self._score_sentence(
                    sentence, i, len(messages), j, msg.role
                )
                scored_sentences.append((sentence, score))

        # Ordenar por score y tomar las mejores
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [s for s, _ in scored_sentences[:10]]

        # Reconstruir en orden temporal
        selected: list[tuple[str, float]] = []
        for sentence, score in scored_sentences[:10]:
            selected.append((sentence, score))

        # Concatenar
        summary = " ".join(s for s, _ in selected[:8])

        # Truncar si excede limite
        if len(summary) > self._config.max_summary_length:
            summary = summary[:self._config.max_summary_length - 3] + "..."

        return summary

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Divide texto en oraciones."""
        # Split por puntos, signos de exclamacion/pregunta
        parts = re.split(r'(?<=[.!?])\s+', text)
        return [p.strip() for p in parts if len(p.strip()) > 10]

    @staticmethod
    def _score_sentence(
        sentence: str,
        msg_index: int,
        total_msgs: int,
        sent_index: int,
        role: MessageRole,
    ) -> float:
        """
        Score de importancia de una oracion.

        Factores:
          - Position (primeras y ultimas oraciones = mas importantes)
          - Length (oraciones muy cortas = menos importantes)
          - Role (mensajes de usuario = mas importantes)
          - Content (preguntas y afirmaciones clave = boost)
        """
        score = 0.0

        # Position boost: primeras y ultimas posiciones
        pos_ratio = msg_index / max(total_msgs, 1)
        if pos_ratio < 0.2:
            score += 0.3  # Inicio de conversacion
        elif pos_ratio > 0.8:
            score += 0.2  # Conversacion reciente

        # First sentence in message = more important
        if sent_index == 0:
            score += 0.2

        # User messages score higher
        if role == MessageRole.USER:
            score += 0.3

        # Length: penalizar muy cortas, premiar medianas
        length = len(sentence)
        if length < 20:
            score -= 0.1
        elif 30 <= length <= 150:
            score += 0.1

        # Content boost: preguntas y codigo
        if "?" in sentence:
            score += 0.2
        if "```" in sentence:
            score += 0.3
        if any(w in sentence.lower() for w in ["importante", "important", "clave", "key", "error"]):
            score += 0.15

        return score
