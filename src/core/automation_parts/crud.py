"""
CoreCRUDMixin — Workflow CRUD + persistence methods for AutomationEngine.

Contains:
  - Database initialization and loading
  - Workflow creation (direct + from natural language)
  - Trigger and action inference helpers
  - Workflow persistence (save / log execution)
"""

import os
import re
import json
import time
import sqlite3
import hashlib
import logging
from typing import Optional, Dict, Any, List

from . import types as _types
from .types import (
    TriggerType, ActionType,
    Trigger, Action, Workflow, WorkflowExecution,
)

logger = logging.getLogger(__name__)


class CoreCRUDMixin:
    """CRUD and persistence methods for AutomationEngine."""

    def _init_db(self):
        """Crea tablas de automatización en SQLite."""
        with sqlite3.connect(_types.DB_PATH) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS workflows (  # nosemgrep: sqlalchemy-execute-raw-query
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                trigger_type TEXT DEFAULT 'schedule',
                trigger_config TEXT DEFAULT '{}',
                conditions TEXT DEFAULT '[]',
                actions TEXT DEFAULT '[]',
                enabled INTEGER DEFAULT 1,
                created_at REAL DEFAULT 0,
                last_run REAL DEFAULT 0,
                run_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS execution_log (  # nosemgrep: sqlalchemy-execute-raw-query
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                started_at REAL DEFAULT 0,
                finished_at REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                actions_executed INTEGER DEFAULT 0,
                actions_failed INTEGER DEFAULT 0,
                output TEXT DEFAULT '',
                error TEXT DEFAULT ''
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_workflow ON execution_log(workflow_id)")  # nosemgrep: sqlalchemy-execute-raw-query

    def _load_workflows(self):
        """Carga workflows desde SQLite."""
        with sqlite3.connect(_types.DB_PATH) as conn:
            rows = conn.execute("SELECT * FROM workflows WHERE enabled=1").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
        for row in rows:
            wf = Workflow(
                id=row[0],
                name=row[1],
                description=row[2],
                trigger=Trigger(
                    type=TriggerType(row[3]),
                    config=json.loads(row[4]),
                ),
                conditions=json.loads(row[5]),
                actions=[Action(type=ActionType(a["type"]), config=a["config"]) for a in json.loads(row[6])],
                enabled=bool(row[7]),
                created_at=row[8],
                last_run=row[9],
                run_count=row[10],
                status=row[11],
            )
            self._workflows[wf.id] = wf

    # ================================================================
    #  WORKFLOW MANAGEMENT
    # ================================================================

    def create_workflow(self, name: str, description: str = "",
                       trigger: Optional[Trigger] = None,
                       actions: Optional[List[Action]] = None,
                       conditions: Optional[List[Dict]] = None) -> Workflow:
        """Crea un nuevo workflow de automatización."""
        wf_id = hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12]

        workflow = Workflow(
            id=wf_id,
            name=name,
            description=description,
            trigger=trigger or Trigger(),
            conditions=conditions or [],
            actions=actions or [],
            created_at=time.time(),
        )

        self._workflows[wf_id] = workflow
        self._save_workflow(workflow)
        return workflow

    def create_from_description(self, description: str) -> Workflow:
        """
        Crea un workflow a partir de una descripción en lenguaje natural.

        Usa ThinkingEngine para entender la descripción y generar
        el trigger, condiciones y acciones apropiados.
        """
        # Analyze with ThinkingEngine
        if self._thinking:
            plan = self._thinking.plan_generation(description)
            # Determine trigger type from description
            trigger = self._infer_trigger(description)
            actions = self._infer_actions(description, plan)
        else:
            trigger = self._fallback_trigger(description)
            actions = self._fallback_actions(description)

        name = self._extract_name(description)
        return self.create_workflow(name, description, trigger, actions)

    def _infer_trigger(self, description: str) -> Trigger:
        """Infiere el trigger a partir de la descripción."""
        desc_lower = description.lower()

        # Schedule patterns
        schedule_keywords = ["cada", "every", "diario", "daily", "semanal", "weekly",
                             "mensual", "monthly", "hora", "hour", "cron", "schedule"]
        if any(kw in desc_lower for kw in schedule_keywords):
            config = self._parse_schedule(description)
            return Trigger(type=TriggerType.SCHEDULE, config=config)

        # Webhook patterns (check before event to avoid substring false matches)
        webhook_keywords = ["webhook", "callback", "http post", "endpoint"]
        if any(kw in desc_lower for kw in webhook_keywords):
            return Trigger(type=TriggerType.WEBHOOK, config={"path": f"/webhook/custom"})

        # Event patterns (use word-boundary matching for short keywords)
        event_keywords = ["cuando", "when", "al detectar", "on event"]
        event_short = ["si", "if"]
        if any(kw in desc_lower for kw in event_keywords) or \
           any(re.search(r'\b' + re.escape(kw) + r'\b', desc_lower) for kw in event_short):
            return Trigger(type=TriggerType.EVENT, config={"event_type": "custom", "description": description[:100]})

        # Default: daily schedule
        return Trigger(type=TriggerType.SCHEDULE, config={"interval": "daily", "hour": 9})

    def _parse_schedule(self, description: str) -> Dict[str, Any]:
        """Parsea una descripción de schedule."""
        desc_lower = description.lower()
        config = {"interval": "daily", "hour": 9, "minute": 0}

        if "diario" in desc_lower or "daily" in desc_lower:
            config["interval"] = "daily"
        elif "semanal" in desc_lower or "weekly" in desc_lower or "lunes" in desc_lower or "monday" in desc_lower:
            config["interval"] = "weekly"
            config["day_of_week"] = "mon"
        elif "mensual" in desc_lower or "monthly" in desc_lower:
            config["interval"] = "monthly"
            config["day"] = 1
        elif "hora" in desc_lower or "hourly" in desc_lower:
            config["interval"] = "hourly"

        # Try to extract hour
        import re
        hour_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(?:am|pm|de la mañana|de la tarde)?', desc_lower)
        if hour_match:
            config["hour"] = int(hour_match.group(1))
            if hour_match.group(2):
                config["minute"] = int(hour_match.group(2))

        return config

    def _infer_actions(self, description: str, plan=None) -> List[Action]:
        """Infiere las acciones a partir de la descripción."""
        actions = []
        desc_lower = description.lower()

        # Email actions
        if any(kw in desc_lower for kw in ["email", "correo", "enviar", "mail"]):
            actions.append(Action(
                type=ActionType.SEND_EMAIL,
                config={"to": "admin@company.com", "subject": "Automated Report", "template": "default"}
            ))

        # Report generation
        if any(kw in desc_lower for kw in ["reporte", "report", "informe"]):
            actions.append(Action(
                type=ActionType.GENERATE_REPORT,
                config={"template": "default_report", "format": "html"}
            ))

        # Database operations
        if any(kw in desc_lower for kw in ["backup", "respaldo", "base de datos", "database"]):
            actions.append(Action(
                type=ActionType.DATABASE_OPERATION,
                config={"operation": "backup", "destination": "backups/"}
            ))

        # Notifications
        if any(kw in desc_lower for kw in ["notificar", "alertar", "notification", "alert"]):
            actions.append(Action(
                type=ActionType.SEND_NOTIFICATION,
                config={"channel": "log", "message": "Alert triggered"}
            ))

        # Data sync
        if any(kw in desc_lower for kw in ["sincronizar", "sync", "integrar", "migrar"]):
            actions.append(Action(
                type=ActionType.DATA_SYNC,
                config={"source": "local_db", "destination": "remote"}
            ))

        # HTTP request
        if any(kw in desc_lower for kw in ["api", "webhook", "http", "request"]):
            actions.append(Action(
                type=ActionType.HTTP_REQUEST,
                config={"url": "https://api.example.com/webhook", "method": "POST"}
            ))

        # Default: if no actions identified, add a notification
        if not actions:
            actions.append(Action(
                type=ActionType.SEND_NOTIFICATION,
                config={"channel": "log", "message": f"Workflow executed: {description[:50]}"}
            ))

        return actions

    def _fallback_trigger(self, description: str) -> Trigger:
        """Fallback trigger inference sin IA."""
        return self._infer_trigger(description)

    def _fallback_actions(self, description: str) -> List[Action]:
        """Fallback action inference sin IA."""
        return self._infer_actions(description)

    def _extract_name(self, description: str) -> str:
        """Extrae un nombre corto de la descripción."""
        # Take first meaningful words
        words = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]', '', description).split()[:4]
        name = "_".join(w.lower() for w in words)
        return name if name else "automation"

    # ================================================================
    #  WORKFLOW PERSISTENCE
    # ================================================================

    def _save_workflow(self, wf: Workflow):
        """Guarda un workflow en SQLite."""
        with sqlite3.connect(_types.DB_PATH) as conn:
            conn.execute("""INSERT OR REPLACE INTO workflows  # nosemgrep: sqlalchemy-execute-raw-query
                (id, name, description, trigger_type, trigger_config, conditions, actions, enabled, created_at, last_run, run_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (wf.id, wf.name, wf.description, wf.trigger.type.value,
                 json.dumps(wf.trigger.config), json.dumps(wf.conditions),
                 json.dumps([{"type": a.type.value, "config": a.config} for a in wf.actions]),
                 int(wf.enabled), wf.created_at, wf.last_run, wf.run_count, wf.status))

    def _log_execution(self, execution: WorkflowExecution):
        """Registra una ejecución en el log."""
        with sqlite3.connect(_types.DB_PATH) as conn:
            conn.execute("""INSERT INTO execution_log  # nosemgrep: sqlalchemy-execute-raw-query
                (workflow_id, started_at, finished_at, status, actions_executed, actions_failed, output, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (execution.workflow_id, execution.started_at, execution.finished_at,
                 execution.status, execution.actions_executed, execution.actions_failed,
                 execution.output, execution.error))
