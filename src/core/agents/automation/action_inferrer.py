"""
A30 ActionInferrer — SINGLE RESPONSIBILITY: Infer action type from description.

Deterministic keyword matching. No AI.
Infers which action types (email, http, db, file, webhook, notification,
transform, schedule, log) are described in natural language (EN + ES).
Unlike triggers, actions can match MULTIPLE types simultaneously.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import AutoDescription, ActionSpec

# ──────────────────────────────────────────────────────────────
# ACTION KEYWORDS — EN + ES bilingual
# ──────────────────────────────────────────────────────────────

ACTION_KEYWORDS: dict[str, list[str]] = {
    "email": [
        "email", "correo", "enviar", "mail", "smtp",
        "notificar por correo", "envío", "envio",
    ],
    "notification": [
        "notificar", "alertar", "notification", "alert", "avisar",
        "push", "slack", "teams",
    ],
    "report": [
        "reporte", "report", "informe", "resumen", "summary",
        "dashboard", "panel",
    ],
    "db": [
        "backup", "respaldo", "base de datos", "database", "db",
        "sql", "consulta", "query", "insertar", "actualizar",
    ],
    "http": [
        "api", "webhook", "http", "request", "endpoint", "servicio",
        "rest", "get", "post", "put",
    ],
    "file": [
        "archivo", "file", "csv", "excel", "documento", "exportar",
        "importar", "download", "descargar", "upload", "subir",
    ],
    "transform": [
        "transformar", "procesar", "convertir", "parse", "etl",
        "limpiar", "clean", "filtrar", "filter", "migrar",
    ],
    "schedule": [
        "programar", "schedule", "planificar", "cron", "calendarizar",
    ],
    "log": [
        "log", "registrar", "audit", "auditoría", "auditoria",
        "historial", "track", "seguimiento",
    ],
}

# Default action configs for each type
DEFAULT_ACTION_CONFIGS: dict[str, dict[str, Any]] = {
    "email": {
        "to": "admin@company.com",
        "subject": "Automated Report",
        "template": "default",
    },
    "notification": {
        "channel": "log",
        "message": "Automation executed",
    },
    "report": {
        "template": "default_report",
        "format": "html",
    },
    "db": {
        "operation": "backup",
        "destination": "backups/",
    },
    "http": {
        "url": "https://api.example.com/webhook",
        "method": "POST",
    },
    "file": {
        "operation": "export",
        "format": "csv",
    },
    "transform": {
        "source_format": "raw",
        "target_format": "structured",
    },
    "schedule": {
        "action": "schedule_next",
    },
    "log": {
        "level": "info",
        "message": "Automation executed",
    },
}

MAX_ACTIONS = 5  # Cap to prevent explosion


class ActionInferrer(BaseAgent[ActionSpec]):
    """
    A30: Infer action types from automation description.

    Single Responsibility: Action inference ONLY.
    Method: Bilingual keyword matching (deterministic), multi-match.
    Fallback: Return a log action (safest default).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A30_ActionInferrer", **kwargs)

    def execute(self, input_data: Any) -> ActionSpec:
        """
        Infer action types from description.

        input_data can be:
          - AutoDescription object
          - dict with 'description' key
          - str (the description itself)

        Returns a SINGLE primary ActionSpec. Use infer_all() for multiple.
        """
        actions = self.infer_all(input_data)
        if actions:
            return actions[0]
        return self.fallback(input_data)

    def infer_all(self, input_data: Any) -> list[ActionSpec]:
        """
        Infer ALL matching action types from description.

        Unlike triggers (first-match-wins), actions can match multiple types.
        Returns up to MAX_ACTIONS actions.
        """
        description = self._extract_description(input_data)

        if not description:
            return [ActionSpec(
                type="log",
                config=DEFAULT_ACTION_CONFIGS["log"],
                description="Default log action (no description)",
                source="deterministic",
            )]

        desc_lower = description.lower()
        actions: list[ActionSpec] = []

        for action_type, keywords in ACTION_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                config = self._build_action_config(action_type, description)
                actions.append(ActionSpec(
                    type=action_type,
                    config=config,
                    description=f"Auto-detected {action_type} action",
                    source="deterministic",
                ))

        # Default: log action if nothing detected
        if not actions:
            actions.append(ActionSpec(
                type="log",
                config={"level": "info", "message": description[:100]},
                description="Default log action (no keywords matched)",
                source="deterministic",
            ))

        return actions[:MAX_ACTIONS]

    def _extract_description(self, input_data: Any) -> str:
        """Extract description string from various input formats."""
        if isinstance(input_data, AutoDescription):
            return input_data.description
        elif isinstance(input_data, dict):
            return input_data.get("description", "")
        elif isinstance(input_data, str):
            return input_data
        return ""

    def _build_action_config(
        self, action_type: str, description: str
    ) -> dict[str, Any]:
        """Build configuration for a detected action type."""
        base_config = DEFAULT_ACTION_CONFIGS.get(action_type, {}).copy()

        # Customize based on description content
        if action_type == "email":
            # Try to extract email addresses
            import re
            email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', description)
            if email_match:
                base_config["to"] = email_match.group(0)

        elif action_type == "http":
            # Try to extract URLs
            import re
            url_match = re.search(r'https?://[\w\-./]+', description)
            if url_match:
                base_config["url"] = url_match.group(0)

        elif action_type == "notification":
            base_config["message"] = description[:100]

        elif action_type == "log":
            base_config["message"] = description[:100]

        return base_config

    def fallback(self, input_data: Any) -> ActionSpec:
        """Fallback: Return a log action (safest default)."""
        return ActionSpec(
            type="log",
            config=DEFAULT_ACTION_CONFIGS["log"],
            source="fallback",
        )
