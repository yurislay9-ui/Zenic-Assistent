"""
A29 TriggerInferrer — SINGLE RESPONSIBILITY: Infer trigger type from description.

Deterministic keyword matching. No AI.
Infers whether a trigger is manual, schedule, event, or webhook
from natural language descriptions (EN + ES bilingual).
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import AutoDescription, TriggerSpec

# ──────────────────────────────────────────────────────────────
# TRIGGER KEYWORDS — EN + ES bilingual
# ──────────────────────────────────────────────────────────────

TRIGGER_KEYWORDS: dict[str, list[str]] = {
    "schedule": [
        "cada", "every", "diario", "daily", "semanal", "weekly",
        "mensual", "monthly", "hora", "hourly", "cron", "schedule",
        "programado", "periódico", "periodico", "a las",
        "minuto", "minute", "segundo", "second",
    ],
    "event": [
        "cuando", "when", "al detectar", "on event",
        "detecte", "ocurra", "trigger", "al recibir",
        "al cambiar", "on change", "on update", "al actualizar",
    ],
    "webhook": [
        "webhook", "callback", "http post", "endpoint", "api call",
        "recibir", "petición", "peticion", "post request",
        "incoming", "entrante",
    ],
}

# Priority order for trigger inference (first match wins)
TRIGGER_PRIORITY = ["webhook", "event", "schedule"]


class TriggerInferrer(BaseAgent[TriggerSpec]):
    """
    A29: Infer trigger type from automation description.

    Single Responsibility: Trigger inference ONLY.
    Method: Bilingual keyword matching (deterministic).
    Fallback: Return manual trigger (safest default).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A29_TriggerInferrer", **kwargs)

    def execute(self, input_data: Any) -> TriggerSpec:
        """
        Infer trigger type from description.

        input_data can be:
          - AutoDescription object
          - dict with 'description' key
          - str (the description itself)
        """
        description = self._extract_description(input_data)

        if not description:
            return TriggerSpec(
                type="manual",
                config={},
                description="No description provided — defaulting to manual trigger",
                source="deterministic",
            )

        # Infer trigger type via keyword matching (priority order)
        for trigger_type in TRIGGER_PRIORITY:
            keywords = TRIGGER_KEYWORDS.get(trigger_type, [])
            if any(kw in description.lower() for kw in keywords):
                config = self._build_trigger_config(trigger_type, description)
                return TriggerSpec(
                    type=trigger_type,
                    config=config,
                    description=f"Auto-detected {trigger_type} trigger",
                    source="deterministic",
                )

        # Default: manual trigger (safest)
        return TriggerSpec(
            type="manual",
            config={},
            description="Manual trigger (no keywords detected)",
            source="deterministic",
        )

    def _extract_description(self, input_data: Any) -> str:
        """Extract description string from various input formats."""
        if isinstance(input_data, AutoDescription):
            return input_data.description
        elif isinstance(input_data, dict):
            return input_data.get("description", "")
        elif isinstance(input_data, str):
            return input_data
        return ""

    def _build_trigger_config(
        self, trigger_type: str, description: str
    ) -> dict[str, Any]:
        """Build configuration dict for the detected trigger type."""
        if trigger_type == "schedule":
            return self._build_schedule_config(description)
        elif trigger_type == "event":
            return {
                "event_type": "custom",
                "description": description[:100],
            }
        elif trigger_type == "webhook":
            return {
                "path": "/webhook/custom",
                "method": "POST",
            }
        return {}

    def _build_schedule_config(self, description: str) -> dict[str, Any]:
        """Build schedule-specific trigger configuration."""
        desc_lower = description.lower()
        config: dict[str, Any] = {"interval": "daily", "hour": 9, "minute": 0}

        if "diario" in desc_lower or "daily" in desc_lower:
            config["interval"] = "daily"
        elif "semanal" in desc_lower or "weekly" in desc_lower:
            config["interval"] = "weekly"
            config["day_of_week"] = "mon"
        elif "mensual" in desc_lower or "monthly" in desc_lower:
            config["interval"] = "monthly"
            config["day"] = 1
        elif "hora" in desc_lower or "hourly" in desc_lower:
            config["interval"] = "hourly"
        elif "minuto" in desc_lower or "minute" in desc_lower:
            config["interval"] = "minutely"

        # Extract specific hour
        hour = self._extract_hour(description)
        if hour != 9:
            config["hour"] = hour

        return config

    @staticmethod
    def _extract_hour(description: str) -> int:
        """Extract hour from description (supports AM/PM and ES phrases)."""
        desc_lower = description.lower()
        match = re.search(
            r"(\d{1,2}):?(\d{2})?\s*(?:am|pm|de la mañana|de la tarde|de la noche)?",
            desc_lower,
        )
        if match:
            hour = int(match.group(1))
            # Spanish PM indicators
            if ("pm" in desc_lower or "de la tarde" in desc_lower or "de la noche" in desc_lower) and hour < 12:
                hour += 12
            # Spanish AM indicators
            elif ("am" in desc_lower or "de la mañana" in desc_lower) and hour == 12:
                hour = 0
            return hour
        return 9

    def fallback(self, input_data: Any) -> TriggerSpec:
        """Fallback: Return manual trigger (safest default)."""
        return TriggerSpec(type="manual", source="fallback")
