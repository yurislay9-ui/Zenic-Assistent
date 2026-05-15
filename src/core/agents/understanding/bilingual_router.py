"""
A48 BilingualRouter — SINGLE RESPONSIBILITY: Detect language and route to EN/ES handlers.

Deterministic keyword matching. No AI.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import LanguageResult

# Spanish indicator words (common words that strongly indicate Spanish)
ES_INDICATORS = [
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "por", "para", "con", "sin", "sobre",
    "que", "como", "donde", "cuando", "cual", "quien",
    "crear", "hacer", "tener", "poder", "decir", "ver",
    "proyecto", "aplicacion", "funcion", "metodo", "clase",
    "base de datos", "interfaz", "usuario", "sistema",
    "necesito", "quiero", "deseo", "ayuda",
]


class BilingualRouter(BaseAgent[LanguageResult]):
    """
    A48: Detect language and route accordingly.

    Single Responsibility: Language detection ONLY.
    Method: Keyword matching (deterministic).
    Fallback: Default to English.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A48_BilingualRouter", **kwargs)
        self._es_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(w) for w in ES_INDICATORS) + r')\b',
            re.IGNORECASE,
        )

    def execute(self, input_data: Any) -> LanguageResult:
        """Detect language from text."""
        text = str(input_data) if input_data else ""
        if not text:
            return self.fallback(input_data)

        # Count Spanish indicator matches
        es_matches = len(self._es_pattern.findall(text))

        # Count total words
        word_count = len(text.split())

        # If >20% of words match Spanish indicators, classify as Spanish
        if word_count > 0 and es_matches / word_count > 0.15:
            lang = "es"
            raw_confidence = min(es_matches / max(word_count * 0.3, 1), 1.0)
            # Cap confidence for short inputs — a single word match is not 100% certain
            if word_count < 5:
                confidence = min(raw_confidence, 0.85)
            else:
                confidence = raw_confidence
        else:
            lang = "en"
            raw_confidence = 1.0 - min(es_matches / max(word_count * 0.3, 1), 0.5)
            if word_count < 3:
                confidence = min(raw_confidence, 0.8)
            else:
                confidence = raw_confidence

        return LanguageResult(
            lang=lang,
            text=text,
            confidence=round(confidence, 2),
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> LanguageResult:
        """Default to English."""
        return LanguageResult(
            lang="en",
            text=str(input_data) if input_data else "",
            confidence=0.5,
            source="fallback",
        )
