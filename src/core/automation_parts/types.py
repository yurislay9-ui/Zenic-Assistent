"""
ZENIC-AGENTS - AutomationEngine Types (Workflow Automation for PYMEs)

Motor de automatizaciones que permite crear flujos de trabajo
automatizados para pequeñas y medianas empresas.

Tipos de automatización:
  1. Scheduled Jobs - Tareas programadas (cron-like)
  2. Event Triggers - Acciones en respuesta a eventos
  3. Data Pipelines - Procesamiento ETL de datos
  4. Notification Workflows - Alertas y notificaciones
  5. Integration Bridges - Conexión entre servicios

Cada automatización se define como un Workflow:
  Trigger → [Conditions] → Actions → [Notifications]

Ejemplos de automatizaciones para PYMEs:
  - "Cada lunes enviar reporte de ventas por email"
  - "Cuando se agote el stock de un producto, notificar"
  - "Sincronizar datos del CRM con la facturación"
  - "Backup automático de la base de datos cada noche"
  - "Monitorear API y alertar si está caída"

Optimizado para:
  - APScheduler para scheduling (lightweight, no Celery needed)
  - SQLite para estado de jobs (persistente)
  - smtplib para emails (sin servicio externo)
  - asyncio para ejecución no-bloqueante
"""

import os
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum


DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
DB_PATH = os.path.join(DB_DIR, "automation.sqlite")
PROJECTS_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "projects")


class TriggerType(str, Enum):
    SCHEDULE = "schedule"        # Cron/schedule trigger
    EVENT = "event"              # Event-based trigger
    WEBHOOK = "webhook"          # HTTP webhook trigger
    FILE_CHANGE = "file_change"  # File system trigger
    DATA_CHANGE = "data_change"  # Database change trigger


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    SEND_NOTIFICATION = "send_notification"
    RUN_SCRIPT = "run_script"
    DATABASE_OPERATION = "database_operation"
    HTTP_REQUEST = "http_request"
    GENERATE_REPORT = "generate_report"
    FILE_OPERATION = "file_operation"
    DATA_SYNC = "data_sync"


@dataclass
class Trigger:
    """Disparador de una automatización."""
    type: TriggerType = TriggerType.SCHEDULE
    config: Dict[str, Any] = field(default_factory=dict)
    # Schedule: {"interval": "daily", "hour": 9, "minute": 0, "day_of_week": "mon"}
    # Event: {"event_type": "stock_low", "threshold": 5}
    # Webhook: {"path": "/webhook/stock-alert"}
    # File: {"path": "/data/*.csv", "event": "created"}


@dataclass
class Action:
    """Acción a ejecutar cuando se dispara el trigger."""
    type: ActionType = ActionType.SEND_NOTIFICATION
    config: Dict[str, Any] = field(default_factory=dict)
    # Email: {"to": "admin@company.com", "subject": "Report", "template": "weekly_report"}
    # Script: {"code": "print('hello')", "language": "python"}
    # DB: {"query": "SELECT * FROM sales WHERE date > ?", "params": []}
    # HTTP: {"url": "https://api.example.com/notify", "method": "POST"}
    # Report: {"template": "sales_report", "format": "html", "recipient": "admin"}
    # File: {"operation": "copy", "source": "/a", "destination": "/b"}


@dataclass
class Workflow:
    """Definición completa de una automatización."""
    id: str = ""
    name: str = ""
    description: str = ""
    trigger: Trigger = field(default_factory=Trigger)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    enabled: bool = True
    created_at: float = 0.0
    last_run: float = 0.0
    run_count: int = 0
    status: str = "active"  # active, paused, error


@dataclass
class WorkflowExecution:
    """Resultado de una ejecución de workflow."""
    workflow_id: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    status: str = "pending"  # pending, running, success, failed
    actions_executed: int = 0
    actions_failed: int = 0
    output: str = ""
    error: str = ""
