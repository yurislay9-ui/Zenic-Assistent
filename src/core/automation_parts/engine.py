"""
AutomationEngine — Main class combining all mixins.

Combines:
  - CoreCRUDMixin: workflow CRUD + persistence
  - ExecutionMixin: workflow execution logic
  - ProjectGenMixin: project generation from natural language

Plus own methods:
  - __init__, list_workflows, get_workflow, toggle_workflow,
    delete_workflow, get_execution_history, stats
"""

import os
import sqlite3
import logging
from typing import Optional, Dict, Any, List

from . import types as _types
from .types import (
    Trigger, Action, Workflow, WorkflowExecution,
)
from .crud import CoreCRUDMixin
from .execution import ExecutionMixin
from .project_gen import ProjectGenMixin

logger = logging.getLogger(__name__)


class AutomationEngine(CoreCRUDMixin, ExecutionMixin, ProjectGenMixin):
    """
    Motor de automatizaciones para PYMEs.

    Permite definir, almacenar y ejecutar flujos de trabajo automatizados.
    Usa APScheduler para scheduling, SQLite para persistencia, y
    ActionExecutor para ejecución REAL de acciones (no logger.info stubs).
    """

    def __init__(self, thinking_engine=None, template_engine=None, executor_registry=None):
        self._thinking = thinking_engine
        self._template_engine = template_engine
        self._executor_registry = executor_registry
        self._workflows: Dict[str, Workflow] = {}
        self._execution_history: List[WorkflowExecution] = []
        os.makedirs(_types.DB_DIR, exist_ok=True)
        self._init_db()
        self._load_workflows()

        # Lazy-init template engine if not provided
        # TemplateEngine removed — module deleted
        if self._template_engine is None:
            self._template_engine = None  # TemplateEngine removed — module deleted

        # Lazy-init executor registry if not provided
        if self._executor_registry is None:
            try:
                from src.core.action_executor import get_default_registry
                self._executor_registry = get_default_registry()
                logger.info("AutomationEngine: ActionExecutor registry initialized")
            except ImportError:
                logger.warning("AutomationEngine: ActionExecutor not available, using legacy stubs")

    # ================================================================
    #  QUERY METHODS
    # ================================================================

    def list_workflows(self) -> List[Dict[str, Any]]:
        """Lista todos los workflows."""
        return [
            {
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "trigger": {"type": wf.trigger.type.value, "config": wf.trigger.config},
                "actions": [{"type": a.type.value, "config": a.config} for a in wf.actions],
                "enabled": wf.enabled,
                "run_count": wf.run_count,
                "last_run": wf.last_run,
                "status": wf.status,
            }
            for wf in self._workflows.values()
        ]

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un workflow por ID."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        return {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "trigger": {"type": wf.trigger.type.value, "config": wf.trigger.config},
            "actions": [{"type": a.type.value, "config": a.config} for a in wf.actions],
            "enabled": wf.enabled,
            "run_count": wf.run_count,
            "status": wf.status,
        }

    def toggle_workflow(self, workflow_id: str) -> bool:
        """Activa/desactiva un workflow."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return False
        wf.enabled = not wf.enabled
        wf.status = "active" if wf.enabled else "paused"
        self._save_workflow(wf)
        return wf.enabled

    def delete_workflow(self, workflow_id: str) -> bool:
        """Elimina un workflow."""
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            with sqlite3.connect(_types.DB_PATH) as conn:
                conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))  # nosemgrep: sqlalchemy-execute-raw-query
            return True
        return False

    def get_execution_history(self, workflow_id: str = "", limit: int = 20) -> List[Dict]:
        """Obtiene historial de ejecuciones."""
        with sqlite3.connect(_types.DB_PATH) as conn:
            if workflow_id:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT * FROM execution_log WHERE workflow_id=? ORDER BY started_at DESC LIMIT ?",
                    (workflow_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT * FROM execution_log ORDER BY started_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()

        return [
            {
                "id": r[0], "workflow_id": r[1], "started_at": r[2],
                "finished_at": r[3], "status": r[4], "actions_executed": r[5],
                "actions_failed": r[6], "output": r[7], "error": r[8],
            }
            for r in rows
        ]

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del motor de automatización."""
        return {
            "total_workflows": len(self._workflows),
            "active_workflows": sum(1 for w in self._workflows.values() if w.enabled),
            "total_executions": len(self._execution_history),
            "successful_executions": sum(1 for e in self._execution_history if e.status == "success"),
        }

    # ── Autopilot Integration (Phase D1) ──────────────────

    def get_autopilot_engine(self):
        """Lazy-load and return the AutopilotEngine (Phase D1)."""
        try:
            from src.core.autopilot import get_autopilot_engine
            return get_autopilot_engine()
        except ImportError:
            logger.warning("AutomationEngine: AutopilotEngine not available")
            return None

    def list_autopilot_objectives(self) -> List[Dict[str, Any]]:
        """List all autopilot objectives and their status."""
        ap = self.get_autopilot_engine()
        if ap is None:
            return []
        try:
            return ap.get_all_objectives_status()
        except Exception:
            return []

    def execute_autopilot_cycle(self) -> List[Dict[str, Any]]:
        """Run one autopilot execution cycle for all active objectives."""
        ap = self.get_autopilot_engine()
        if ap is None:
            return []
        try:
            return ap.check_and_execute()
        except Exception as e:
            logger.error("AutomationEngine: Autopilot cycle failed: %s", e)
            return []
