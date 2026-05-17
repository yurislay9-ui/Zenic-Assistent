"""
Sanitizador de entrada del Asistente.

Limpia y valida el mensaje del usuario antes de
cualquier procesamiento. Garantiza que el texto
entrante es seguro y esta bien formado.

Responsabilidades:
  - Trim y normalizacion de espacios
  - Deteccion de inyecciones de prompt
  - Limites de longitud
  - Normalizacion de caracteres especiales
  - Deteccion de idioma basica
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..types.base import Result, Ok, Err, Priority


# ─── Config ──────────────────────────────────────────────────

@dataclass
class SanitizerConfig:
    """Configuracion del sanitizador."""
    max_length: int = 10000
    min_length: int = 1
    max_newlines: int = 50
    max_repeated_chars: int = 10
    strip_control_chars: bool = True
    detect_injection: bool = True
    normalize_unicode: bool = True


# ─── Resultado de sanitizacion ───────────────────────────────

@dataclass
class SanitizedInput:
    """Resultado del proceso de sanitizacion."""
    original: str = ""
    cleaned: str = ""
    was_modified: bool = False
    detected_language: str = "es"
    priority: Priority = Priority.NORMAL
    warnings: list[str] = field(default_factory=list)
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    has_code_blocks: bool = False
    has_urls: bool = False

    @property
    def is_empty(self) -> bool:
        return len(self.cleaned.strip()) == 0


# ─── Patrones de inyeccion ───────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous\s+)?(instructions|rules)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"###\s*system", re.IGNORECASE),
]

_CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


class InputSanitizer:
    """
    Sanitizador de entrada.

    Aplica transformaciones secuenciales para garantizar
    que el input es seguro y bien formado. Cada transformacion
    es independiente y composable.
    """

    def __init__(self, config: SanitizerConfig | None = None) -> None:
        self._config = config or SanitizerConfig()

    def sanitize(self, raw_input: str) -> Result[SanitizedInput, Exception]:
        """
        Sanitiza el input del usuario.

        Pipeline: validate → clean → analyze → detect.

        Returns:
            Ok(SanitizedInput) si el input es valido.
            Err(ValueError) si el input es invalido.
        """
        # 1. Validacion de longitud
        if not raw_input or len(raw_input.strip()) < self._config.min_length:
            return Err(ValueError("El mensaje esta vacio"))

        if len(raw_input) > self._config.max_length:
            return Err(ValueError(
                f"Mensaje excede {self._config.max_length} caracteres"
            ))

        # 2. Limpieza
        cleaned, was_modified = self._clean(raw_input)

        # 3. Deteccion de inyeccion
        warnings: list[str] = []
        if self._config.detect_injection:
            injection = self._detect_injection(cleaned)
            if injection:
                warnings.append(injection)

        # 4. Analisis
        lang = self._detect_language(cleaned)
        has_code = bool(_CODE_BLOCK_PATTERN.search(raw_input))
        has_urls = bool(_URL_PATTERN.search(raw_input))

        # 5. Prioridad
        priority = self._infer_priority(cleaned, has_code, warnings)

        return Ok(SanitizedInput(
            original=raw_input,
            cleaned=cleaned,
            was_modified=was_modified,
            detected_language=lang,
            priority=priority,
            warnings=warnings,
            char_count=len(cleaned),
            word_count=len(cleaned.split()),
            line_count=cleaned.count("\n") + 1,
            has_code_blocks=has_code,
            has_urls=has_urls,
        ))

    # ─── Limpieza ─────────────────────────────────────────────

    def _clean(self, text: str) -> tuple[str, bool]:
        """
        Aplica transformaciones de limpieza.

        Returns:
            (texto_limpio, fue_modificado)
        """
        modified = False
        result = text

        # Trim
        trimmed = result.strip()
        if trimmed != result:
            result = trimmed
            modified = True

        # Normalizar unicode
        if self._config.normalize_unicode:
            normalized = unicodedata.normalize("NFC", result)
            if normalized != result:
                result = normalized
                modified = True

        # Strip control chars (preservar newlines y tabs)
        if self._config.strip_control_chars:
            cleaned = "".join(
                ch for ch in result
                if ch.isprintable() or ch in ("\n", "\t")
            )
            if cleaned != result:
                result = cleaned
                modified = True

        # Colapsar espacios multiples (no dentro de code blocks)
        collapsed = re.sub(r"[^\S\n]+", " ", result)
        if collapsed != result:
            result = collapsed
            modified = True

        # Limitar newlines consecutivos
        limited = re.sub(r"\n{3,}", "\n\n", result)
        if limited != result:
            result = limited
            modified = True

        return result, modified

    # ─── Deteccion ─────────────────────────────────────────────

    @staticmethod
    def _detect_injection(text: str) -> str | None:
        """Detecta patrones de inyeccion de prompt."""
        # No sanitar dentro de code blocks
        code_blocks = list(_CODE_BLOCK_PATTERN.finditer(text))
        text_without_code = text
        for match in reversed(code_blocks):
            text_without_code = (
                text_without_code[:match.start()]
                + text_without_code[match.end():]
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text_without_code):
                return f"Posible intento de inyeccion detectado: {pattern.pattern}"
        return None

    @staticmethod
    def _detect_language(text: str) -> str:
        """Deteccion basica de idioma por caracteres."""
        spanish_markers = [
            "ñ", "á", "é", "í", "ó", "ú", "ü",
            "que", "el", "la", "los", "las",
            "de", "en", "es", "un", "una",
        ]
        english_markers = [
            "the", "is", "are", "was", "were",
            "and", "but", "for", "not", "you",
        ]

        text_lower = text.lower()
        es_score = sum(1 for m in spanish_markers if m in text_lower)
        en_score = sum(1 for m in english_markers if m in text_lower)

        if es_score > en_score:
            return "es"
        if en_score > es_score:
            return "en"
        return "es"  # Default

    @staticmethod
    def _infer_priority(
        text: str, has_code: bool, warnings: list[str]
    ) -> Priority:
        """Infiere la prioridad del mensaje."""
        if warnings:
            return Priority.HIGH

        text_lower = text.lower()
        urgent = ["urgente", "urgent", "error critico", "critical", "asap"]
        if any(w in text_lower for w in urgent):
            return Priority.CRITICAL

        if has_code:
            return Priority.HIGH

        return Priority.NORMAL
