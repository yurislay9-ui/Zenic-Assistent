"""
Mixin: Fallback and deterministic inference methods.
"""

import re
import time
import json
import dataclasses
from typing import Any, Dict, List, Optional

from ._imports import (
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
    TRIGGER_KEYWORDS, ACTION_KEYWORDS, SCHEDULE_PATTERNS, logger,
)


class FallbackMixin:
    """Fallback, deterministic inference for AutomationAgent."""

    def fallback(self, input_data: Any) -> AutomationOutput:
        """
        Fallback determinista: inferencia por keywords.

        Sin LLM, sin embeddings. Detección directa de triggers, acciones
        y schedules desde keywords en la descripción.
        """
        start = time.time()

        if isinstance(input_data, AutomationInput):
            description = input_data.description
            context = input_data.context
        else:
            description = str(input_data)
            context = {}

        # 1. SmartMemory lookup
        if self._smart_memory:
            try:
                cached = self._smart_memory.check_cache(description)
                if cached and cached.get("response"):
                    duration_ms = int((time.time() - start) * 1000)
                    self._update_stats("fallback", duration_ms)
                    # Try to parse cached response as automation (safe parsing)
                    try:
                        cached_data = json.loads(cached["response"])
                        if isinstance(cached_data, dict):
                            return self._json_to_automation_output(cached_data, source="fallback")
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
            except Exception:
                pass

        # 2. Deterministic inference
        triggers = self._infer_triggers(description)
        actions = self._infer_actions(description)
        schedule = self._infer_schedule(description)
        name = self._extract_name(description)
        conditions = self._infer_conditions(description)

        # Save to memory
        if self._smart_memory:
            try:
                self._smart_memory.save_to_cache(
                    description, json.dumps(dataclasses.asdict(AutomationOutput(
                        name=name, triggers=triggers, actions=actions,
                        schedule=schedule, conditions=conditions,
                        description=description[:200],
                    ))), "automation", "", 0.6,
                )
            except Exception:
                pass

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        return AutomationOutput(
            name=name,
            triggers=triggers,
            actions=actions,
            schedule=schedule,
            conditions=conditions,
            description=description[:200],
            source="fallback",
        )

    # ------------------------------------------------------------------
    #  Deterministic inference helpers
    # ------------------------------------------------------------------

    def _infer_triggers(self, description: str) -> List[TriggerSpec]:
        """Infiere triggers desde la descripción por keywords."""
        desc_lower = description.lower()

        for trigger_type, keywords in TRIGGER_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                config = {}
                if trigger_type == "schedule":
                    config = self._parse_schedule_config(description)
                elif trigger_type == "event":
                    config = {"event_type": "custom", "description": description[:100]}
                elif trigger_type == "webhook":
                    config = {"path": "/webhook/custom"}

                return [TriggerSpec(
                    type=trigger_type,
                    config=config,
                    description=f"Auto-detected {trigger_type} trigger",
                )]

        # Default: daily schedule
        return [TriggerSpec(
            type="schedule",
            config={"interval": "daily", "hour": 9},
            description="Default daily schedule",
        )]

    def _infer_actions(self, description: str) -> List[ActionSpec]:
        """Infiere acciones desde la descripción por keywords."""
        desc_lower = description.lower()
        actions = []

        for action_type, keywords in ACTION_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                config = self._default_action_config(action_type, description)
                actions.append(ActionSpec(
                    type=action_type,
                    config=config,
                    description=f"Auto-detected {action_type} action",
                ))

        # Default: log notification if no actions detected
        if not actions:
            actions.append(ActionSpec(
                type="log",
                config={"message": f"Automation executed: {description[:50]}"},
                description="Default log action",
            ))

        return actions[:5]  # Max 5 actions

    def _infer_schedule(self, description: str) -> ScheduleSpec:
        """Infiere schedule desde la descripción."""
        desc_lower = description.lower()

        for sched_type, keywords in SCHEDULE_PATTERNS.items():
            if any(kw in desc_lower for kw in keywords):
                if sched_type == "hourly":
                    return ScheduleSpec(
                        type="interval", interval_seconds=3600,
                        description="Hourly execution",
                    )
                elif sched_type == "daily":
                    hour = self._extract_hour(description)
                    cron = f"0 {hour} * * *"
                    return ScheduleSpec(
                        type="cron", cron_expression=cron,
                        description=f"Daily at {hour}:00",
                    )
                elif sched_type == "weekly":
                    return ScheduleSpec(
                        type="cron", cron_expression="0 9 * * 1",
                        description="Weekly on Monday at 9:00",
                    )
                elif sched_type == "monthly":
                    return ScheduleSpec(
                        type="cron", cron_expression="0 9 1 * *",
                        description="Monthly on the 1st at 9:00",
                    )

        return ScheduleSpec(
            type="manual",
            description="Manual execution",
        )

    def _infer_conditions(self, description: str) -> List[str]:
        """Infiere condiciones desde la descripción."""
        conditions = []
        desc_lower = description.lower()

        if any(kw in desc_lower for kw in ["si", "if", "solo si", "only when"]):
            # Extract condition from "if/when X" pattern
            for pattern in [r'(?:si|if|when)\s+(.+?)(?:\s+(?:then|entonces|,|\.|$))',
                           r'(?:solo si|only when)\s+(.+?)(?:,|\.|$)']:
                match = re.search(pattern, desc_lower)
                if match:
                    conditions.append(match.group(1).strip()[:100])
                    break

        return conditions

    def _extract_name(self, description: str) -> str:
        """Extrae un nombre corto de la descripción."""
        words = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]', '', description).split()[:4]
        stop = {'un', 'una', 'el', 'la', 'los', 'las', 'a', 'de', 'del',
                'en', 'por', 'para', 'con', 'que', 'se', 'the', 'a', 'an',
                'create', 'make', 'generate', 'build', 'automate'}
        name_parts = [w.lower() for w in words if w.lower() not in stop]
        return "_".join(name_parts) if name_parts else "automation"

    # ------------------------------------------------------------------
    #  Schedule parsing helpers
    # ------------------------------------------------------------------

    def _parse_schedule_config(self, description: str) -> Dict[str, Any]:
        """Parsea configuración de schedule desde descripción."""
        config = {"interval": "daily", "hour": 9, "minute": 0}
        desc_lower = description.lower()

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

        # Extract hour
        hour = self._extract_hour(description)
        if hour != 9:
            config["hour"] = hour

        return config

    def _extract_hour(self, description: str) -> int:
        """Extrae hora desde descripción."""
        match = re.search(
            r'(\d{1,2}):?(\d{2})?\s*(?:am|pm|de la mañana|de la tarde)?',
            description.lower(),
        )
        if match:
            hour = int(match.group(1))
            if "pm" in description.lower() and hour < 12:
                hour += 12
            elif "am" in description.lower() and hour == 12:
                hour = 0
            return hour
        return 9

    def _default_action_config(self, action_type: str,
                                description: str) -> Dict[str, Any]:
        """Configuración por defecto para cada tipo de acción."""
        configs = {
            "email": {"to": "admin@company.com", "subject": "Automated Report",
                      "template": "default"},
            "notification": {"channel": "log", "message": description[:100]},
            "report": {"template": "default_report", "format": "html"},
            "db": {"operation": "backup", "destination": "backups/"},
            "http": {"url": "https://api.example.com/webhook", "method": "POST"},
            "file": {"operation": "export", "format": "csv"},
            "transform": {"source_format": "raw", "target_format": "structured"},
            "schedule": {"action": "schedule_next"},
            "log": {"level": "info", "message": description[:100]},
        }
        return configs.get(action_type, {"description": description[:100]})
