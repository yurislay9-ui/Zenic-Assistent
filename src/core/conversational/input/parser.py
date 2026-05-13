"""
Parser de entrada del Asistente.

Extrae estructura y entidades del mensaje sanitizado:
  - Entidades (nombres, archivos, comandos)
  - Estructura (pregunta, instruccion, codigo)
  - Keywords relevantes para clasificacion
  - Fragmentos de codigo y su lenguaje

Todo parser es stateless y determinista.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ...types.base import Result, Ok


# ─── Entidades extraidas ─────────────────────────────────────

@dataclass
class Entity:
    """Entidad extraida del texto."""
    text: str
    entity_type: str      # file, command, language, keyword, url, number
    start: int = 0
    end: int = 0
    confidence: float = 1.0


@dataclass
class ParsedInput:
    """Resultado del parsing."""
    text: str = ""
    normalized: str = ""          # Lowercase, sin acentos para matching
    entities: list[Entity] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    code_snippets: list[dict[str, str]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    is_question: bool = False
    is_command: bool = False
    is_greeting: bool = False
    is_code_request: bool = False
    sentence_count: int = 0
    dominant_language: str = "es"

    @property
    def has_entities(self) -> bool:
        return len(self.entities) > 0

    @property
    def has_code(self) -> bool:
        return len(self.code_snippets) > 0

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        """Filtra entidades por tipo."""
        return [e for e in self.entities if e.entity_type == entity_type]


# ─── Patrones de extraccion ──────────────────────────────────

_FILE_PATTERN = re.compile(
    r"\b[\w.-]+\.(py|js|ts|tsx|jsx|json|yaml|yml|toml|md|txt|sql|sh|bash|"
    r"go|rs|java|cpp|c|h|rb|php|css|html|xml|dockerfile|makefile)\b",
    re.IGNORECASE,
)

_CODE_FENCE_PATTERN = re.compile(
    r"```(\w*)\n([\s\S]*?)```",
    re.MULTILINE,
)

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"]+",
    re.IGNORECASE,
)

_COMMAND_PATTERN = re.compile(
    r"^[/%](\w+)",          # /comando o %comando al inicio
    re.MULTILINE,
)

_QUESTION_MARKERS = {
    "es": ["que", "como", "por que", "cual", "cuando", "donde", "quien", "cuanto"],
    "en": ["what", "how", "why", "which", "when", "where", "who", "how much"],
}

_GREETING_MARKERS = [
    "hola", "hey", "hi", "hello", "buenos", "buenas", "que tal",
    "good morning", "good evening",
]

_CODE_REQUEST_MARKERS = [
    "crear", "generar", "create", "build", "make",
    "escribir", "write", "implementar", "implement",
    "codigo", "code", "script", "modulo", "module",
    "funcion", "function", "clase", "class",
]


class InputParser:
    """
    Parser de entrada.

    Extracciona estructura y entidades del texto
    sanitizado. Statelesss y determinista.
    """

    def parse(self, text: str, language: str = "es") -> Result[ParsedInput]:
        """
        Parsea el texto sanitizado.

        Pipeline: normalize → extract → classify → enrich.

        Returns:
            Ok(ParsedInput) siempre (parsing no falla).
        """
        normalized = self._normalize(text)

        # Extraccion
        entities = self._extract_entities(text, normalized)
        keywords = self._extract_keywords(normalized, language)
        code_snippets = self._extract_code(text)
        urls = self._extract_urls(text)

        # Clasificacion
        is_question = self._is_question(text, normalized, language)
        is_command = self._is_command(text)
        is_greeting = self._is_greeting(normalized)
        is_code_request = self._is_code_request(normalized)

        return Ok(ParsedInput(
            text=text,
            normalized=normalized,
            entities=entities,
            keywords=keywords,
            code_snippets=code_snippets,
            urls=urls,
            is_question=is_question,
            is_command=is_command,
            is_greeting=is_greeting,
            is_code_request=is_code_request,
            sentence_count=text.count(".") + text.count("?") + text.count("!") + 1,
            dominant_language=language,
        ))

    # ─── Normalizacion ────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """Normaliza texto para matching: lowercase, sin acentos."""
        import unicodedata
        result = text.lower()
        # Quitar acentos
        nfkd = unicodedata.normalize("NFD", result)
        result = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
        return result

    # ─── Extraccion ───────────────────────────────────────────

    @staticmethod
    def _extract_entities(text: str, normalized: str) -> list[Entity]:
        """Extrae entidades del texto."""
        entities: list[Entity] = []

        # Archivos
        for match in _FILE_PATTERN.finditer(text):
            entities.append(Entity(
                text=match.group(),
                entity_type="file",
                start=match.start(),
                end=match.end(),
                confidence=0.9,
            ))

        # Comandos
        for match in _COMMAND_PATTERN.finditer(text):
            entities.append(Entity(
                text=match.group(1),
                entity_type="command",
                start=match.start(),
                end=match.end(),
                confidence=0.95,
            ))

        # Numeros significativos
        for match in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
            num_str = match.group()
            if len(num_str) > 1:  # Ignorar digitos sueltos
                entities.append(Entity(
                    text=num_str,
                    entity_type="number",
                    start=match.start(),
                    end=match.end(),
                    confidence=0.7,
                ))

        return entities

    @staticmethod
    def _extract_keywords(normalized: str, language: str) -> list[str]:
        """Extrae keywords relevantes (stop words removidas)."""
        _STOP_WORDS_ES = {
            "el", "la", "los", "las", "de", "en", "es", "un", "una",
            "y", "o", "a", "por", "para", "con", "que", "se", "su",
            "al", "del", "lo", "le", "mas", "ya", "no", "si", "mi",
        }
        _STOP_WORDS_EN = {
            "the", "is", "are", "was", "were", "a", "an", "and",
            "or", "but", "in", "on", "at", "to", "for", "of", "with",
            "it", "its", "this", "that", "i", "you", "he", "she",
        }

        stop = _STOP_WORDS_ES if language == "es" else _STOP_WORDS_EN
        words = re.findall(r"\b\w{3,}\b", normalized)
        return [w for w in words if w not in stop]

    @staticmethod
    def _extract_code(text: str) -> list[dict[str, str]]:
        """Extrae bloques de codigo con su lenguaje."""
        snippets: list[dict[str, str]] = []
        for match in _CODE_FENCE_PATTERN.finditer(text):
            lang = match.group(1) or "unknown"
            code = match.group(2).strip()
            if code:
                snippets.append({"language": lang, "code": code})
        return snippets

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        """Extrae URLs del texto."""
        return _URL_PATTERN.findall(text)

    # ─── Clasificacion ────────────────────────────────────────

    @staticmethod
    def _is_question(text: str, normalized: str, language: str) -> bool:
        """Detecta si el mensaje es una pregunta."""
        if "?" in text:
            return True
        markers = _QUESTION_MARKERS.get(language, _QUESTION_MARKERS["es"])
        return any(m in normalized for m in markers)

    @staticmethod
    def _is_command(text: str) -> bool:
        """Detecta si el mensaje es un comando."""
        return bool(_COMMAND_PATTERN.match(text.strip()))

    @staticmethod
    def _is_greeting(normalized: str) -> bool:
        """Detecta si el mensaje es un saludo."""
        return any(g in normalized for g in _GREETING_MARKERS)

    @staticmethod
    def _is_code_request(normalized: str) -> bool:
        """Detecta si el mensaje es una solicitud de codigo."""
        return any(m in normalized for m in _CODE_REQUEST_MARKERS)
