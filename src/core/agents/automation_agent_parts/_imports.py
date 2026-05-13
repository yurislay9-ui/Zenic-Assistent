"""
Shared imports and constants for automation_agent_parts.
"""

import re
import json
import time
import logging
import dataclasses
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import (
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
)
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Trigger inference keywords (EN + ES)
TRIGGER_KEYWORDS = {
    "schedule": [
        "cada", "every", "diario", "daily", "semanal", "weekly",
        "mensual", "monthly", "hora", "hourly", "cron", "schedule",
        "programado", "periódico", "periodico", "a las",
    ],
    "event": [
        "cuando", "when", "si", "if", "al detectar", "on event",
        "detecte", "ocurra", "trigger",
    ],
    "webhook": [
        "webhook", "callback", "http post", "endpoint", "api call",
        "recibir", "petición",
    ],
}

# Action inference keywords (EN + ES)
ACTION_KEYWORDS = {
    "email": ["email", "correo", "enviar", "mail", "smtp", "notificar por correo"],
    "notification": ["notificar", "alertar", "notification", "alert", "avisar"],
    "report": ["reporte", "report", "informe", "resumen", "summary"],
    "db": ["backup", "respaldo", "base de datos", "database", "db", "sql"],
    "http": ["api", "webhook", "http", "request", "endpoint", "servicio"],
    "file": ["archivo", "file", "csv", "excel", "documento", "exportar"],
    "transform": ["transformar", "procesar", "convertir", "parse", "etl"],
    "schedule": ["programar", "schedule", "planificar", "cron"],
    "log": ["log", "registrar", "audit", "auditoría"],
}

# Schedule parsing patterns
SCHEDULE_PATTERNS = {
    "hourly": ["cada hora", "hourly", "cada 1 hora", "every hour"],
    "daily": ["diario", "daily", "cada día", "cada dia", "every day"],
    "weekly": ["semanal", "weekly", "cada semana", "lunes", "monday", "mon"],
    "monthly": ["mensual", "monthly", "cada mes"],
}
