"""
Clasificador de intencion del asistente.

Detecta la intencion del mensaje del usuario usando
scoring determinista basado en keywords, similar a
IntentClassifier de Zenic-Agents pero expandido para
categorias conversacionales.
"""

from __future__ import annotations

from typing import Any

from ...types.session import Session
from ...types.intent import AssistantIntent, IntentCategory, ConversationMode


# ─── Patrones de intencion ────────────────────────────────────

CHAT_PATTERNS: list[str] = [
    "hola", "hey", "buenos dias", "buenas tardes", "que tal",
    "hi", "hello", "good morning", "how are you",
    "gracias", "thanks", "ok", "bien", "perfecto",
]

QUESTION_PATTERNS: list[str] = [
    "que es", "que significa", "como se", "por que",
    "what is", "how does", "why", "explain", "explica",
    "cual es la diferencia", "difference between",
]

COMMAND_PATTERNS: list[str] = [
    "limpiar", "reset", "borrar", "clear",
    "cambiar idioma", "change language", "cambiar tono",
    "ayuda", "help", "comandos", "estado", "status",
]

CONFIG_PATTERNS: list[str] = [
    "configura", "ajusta", "cambia la personalidad",
    "configure", "adjust", "change personality",
    "modo tecnico", "modo casual", "technical mode",
    "cambiar idioma", "cambiar tono", "cambiar personalidad",
    "change language", "change tone", "change personality",
]

FEEDBACK_PATTERNS: list[str] = [
    "no me gusta", "mal", "incorrecto", "wrong",
    "me gusta", "bien", "correcto", "good",
    "intenta de nuevo", "try again",
]

CODE_CREATE_PATTERNS: list[str] = [
    "crear", "generar", "create", "build", "make", "nuevo modulo",
]
CODE_DEBUG_PATTERNS: list[str] = [
    "debug", "fix", "corregir", "error", "bug", "arreglar",
]
CODE_REFACTOR_PATTERNS: list[str] = [
    "refactor", "limpiar codigo", "reestructurar",
]
CODE_OPTIMIZE_PATTERNS: list[str] = [
    "optimizar", "optimize", "mejorar rendimiento", "speed up",
]

# Mapa de categoria → patrones + peso
PATTERN_MAP: dict[IntentCategory, tuple[list[str], float]] = {
    IntentCategory.CHAT: (CHAT_PATTERNS, 2.0),
    IntentCategory.QUESTION: (QUESTION_PATTERNS, 2.0),
    IntentCategory.COMMAND: (COMMAND_PATTERNS, 2.0),
    IntentCategory.CONFIG: (CONFIG_PATTERNS, 2.5),
    IntentCategory.FEEDBACK: (FEEDBACK_PATTERNS, 2.0),
    IntentCategory.CODE_CREATE: (CODE_CREATE_PATTERNS, 3.0),
    IntentCategory.CODE_DEBUG: (CODE_DEBUG_PATTERNS, 3.0),
    IntentCategory.CODE_REFACTOR: (CODE_REFACTOR_PATTERNS, 3.0),
    IntentCategory.CODE_OPTIMIZE: (CODE_OPTIMIZE_PATTERNS, 3.0),
}


class IntentClassifier:
    """
    Clasificador de intencion para el asistente.

    Usa scoring determinista basado en keywords con pesos.
    Las categorias de codigo tienen peso mayor (3.0) que
    las conversacionales (2.0) para priorizar correctamente.
    """

    def classify(self, message: str, session: Session) -> AssistantIntent:
        """
        Clasifica la intencion de un mensaje.

        Args:
            message: Mensaje del usuario.
            session: Sesion activa (para idioma y contexto).

        Returns:
            AssistantIntent con categoria y confianza.
        """
        text = message.lower().strip()
        scores: dict[IntentCategory, float] = {}

        for category, (patterns, weight) in PATTERN_MAP.items():
            score = 0.0
            for pattern in patterns:
                if pattern in text:
                    score += weight
            if score > 0:
                scores[category] = score

        # Determinar mejor categoria
        if not scores:
            category = IntentCategory.CHAT
            confidence = 0.3
        else:
            category = max(scores, key=scores.get)  # type: ignore
            max_score = scores[category]
            confidence = min(max_score / 8.0, 1.0)

        # Inferir modo de conversacion
        mode = self._infer_mode(category, text)

        return AssistantIntent(
            category=category,
            confidence=confidence,
            mode=mode,
            raw_text=message,
            language=session.config.language,
        )

    @staticmethod
    def _infer_mode(category: IntentCategory, text: str) -> ConversationMode:
        """Infiere el modo de conversacion basado en la categoria."""
        if category in (
            IntentCategory.CODE_CREATE,
            IntentCategory.CODE_DEBUG,
            IntentCategory.CODE_REFACTOR,
            IntentCategory.CODE_OPTIMIZE,
        ):
            return ConversationMode.CODING

        if category == IntentCategory.QUESTION:
            # Si contiene palabras de paso a paso
            step_words = ["paso a paso", "step by step", "explica", "explain"]
            if any(w in text for w in step_words):
                return ConversationMode.TEACHING
            return ConversationMode.REASONING

        if category == IntentCategory.AUTOMATION:
            return ConversationMode.AUTOMATION

        return ConversationMode.NORMAL
