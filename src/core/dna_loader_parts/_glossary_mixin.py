"""
Professional glossary API mixin for DNALoader.
"""

import re
import logging
from typing import Dict

from ._imports import logger


class GlossaryMixin:
    """Mixin with professional glossary API methods."""

    # ================================================================
    #  PROFESSIONAL GLOSSARY API
    # ================================================================

    def _preserve_case_replace(self, match, replacement):
        """Replace a match while preserving the original capitalization pattern."""
        original = match.group(0)
        if original.isupper():
            return replacement.upper()
        elif original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        elif original.islower():
            return replacement.lower()
        return replacement

    def polish_text(self, text: str) -> str:
        """
        Transforma jerga técnica en lenguaje corporativo de élite.

        Aplica todas las transformaciones del glosario profesional.
        Preserves original capitalization and processes longest terms first
        to avoid substring corruption (e.g., "debug" matching "bug").
        """
        if not self._loaded:
            self.load_all()

        result = text
        sorted_entries = sorted(self._glossary, key=lambda e: len(e.from_term), reverse=True)
        for entry in sorted_entries:
            # Case-insensitive replacement preserving original capitalization
            result = re.sub(
                re.escape(entry.from_term),
                lambda m: self._preserve_case_replace(m, entry.to_term),
                result,
                flags=re.IGNORECASE
            )

        return result

    def polish_error(self, error_message: str) -> str:
        """Transforma un mensaje de error técnico en uno profesional."""
        if not self._loaded:
            self.load_all()

        # Direct match
        if error_message in self._error_messages:
            return self._error_messages[error_message]

        # Partial match
        error_lower = error_message.lower()
        for original, polished in self._error_messages.items():
            if original.lower() in error_lower:
                return polished

        return error_message

    def describe_feature(self, technical_name: str) -> Dict[str, str]:
        """Obtiene la descripción de marketing de una feature."""
        if not self._loaded:
            self.load_all()

        if technical_name in self._feature_descriptions:
            return self._feature_descriptions[technical_name]

        # Partial match
        tech_lower = technical_name.lower()
        for key, value in self._feature_descriptions.items():
            if tech_lower in key.lower() or key.lower() in tech_lower:
                return value

        return {"marketing": technical_name, "benefit": ""}
