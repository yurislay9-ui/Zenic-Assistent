"""
Mixin: JSON and free-text parsing helpers for IntentAgent.
"""

from typing import Any, Dict, Optional

from ._imports import IntentOutput, VALID_OPERATIONS, VALID_GOALS, VALID_LANGUAGES


class ParseMixin:
    """_json_to_intent_output and _parse_free_text for IntentAgent."""

    def _json_to_intent_output(self, data: Dict[str, Any],
                               source: str = "llm") -> Optional[IntentOutput]:
        """Convierte un dict JSON a IntentOutput, validando campos."""
        operation = data.get("operation", "").upper()
        goal = data.get("goal", "").upper()

        if operation not in VALID_OPERATIONS:
            operation = "SEARCH"
        if goal not in VALID_GOALS:
            goal = "FEATURE_ADD"

        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {"raw": str(entities)}

        language = data.get("language", "python").lower()
        if language not in VALID_LANGUAGES:
            language = "python"

        target = str(data.get("target", "")).strip()
        template_type = str(data.get("template_type", "generic")).strip()
        criticality = str(data.get("criticality", "standard")).strip()
        if criticality not in ("standard", "moderate", "critical"):
            criticality = "standard"

        return IntentOutput(
            operation=operation,
            goal=goal,
            target=target,
            language=language,
            entities=entities,
            template_type=template_type,
            criticality=criticality,
            confidence=confidence,
            source=source,
        )

    def _parse_free_text(self, text: str, source: str = "llm") -> Optional[IntentOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        text_upper = text.upper().strip()

        # Intentar encontrar operación
        operation = "SEARCH"
        for op in VALID_OPERATIONS:
            if op in text_upper:
                operation = op
                break

        # Intentar encontrar goal
        goal = "FEATURE_ADD"
        for g in VALID_GOALS:
            if g in text_upper:
                goal = g
                break

        # Confidence baja para texto libre parseado
        return IntentOutput(
            operation=operation,
            goal=goal,
            confidence=0.4,
            source=source,
        )
