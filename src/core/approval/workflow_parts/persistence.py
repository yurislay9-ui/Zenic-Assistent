"""
Zenic-Agents Asistente - Workflow Persistence & Built-ins (Phase 6.1c)

Database operations and built-in workflow definitions.
Extracted from workflows.py for the 400-line limit.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from ..workflows import WorkflowDefinition, WorkflowStep, WorkflowStepType, WorkflowExecution

logger = logging.getLogger(__name__)


class WorkflowDB:
    """Database operations for the WorkflowEngine."""

    def __init__(self, db_path: str = "approval_workflows.sqlite") -> None:
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the workflow database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    steps TEXT NOT NULL,
                    trigger_actions TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    tenant_id TEXT DEFAULT '__anonymous__',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    execution_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    current_step_index INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'in_progress',
                    action_type TEXT,
                    action_config TEXT,
                    requested_by INTEGER,
                    step_results TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                )
            """)
            conn.commit()
            conn.close()
            logger.info("WorkflowDB: Database initialized")
        except Exception as exc:
            logger.error("WorkflowDB: DB init failed: %s", exc)

    def create_workflow(self, workflow: WorkflowDefinition) -> None:
        """Persist a new workflow."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO workflows
                   (workflow_id, name, description, steps,
                    trigger_actions, is_active, tenant_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    workflow.workflow_id, workflow.name, workflow.description,
                    json.dumps([s.to_dict() for s in workflow.steps]),
                    json.dumps(workflow.trigger_actions),
                    1 if workflow.is_active else 0,
                    workflow.tenant_id, workflow.created_at,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("WorkflowDB: Create failed: %s", exc)

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get a workflow by ID."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_workflow(row)
        except Exception:
            return None

    def list_workflows(
        self, tenant_id: Optional[str] = None, active_only: bool = True,
    ) -> List[WorkflowDefinition]:
        """List workflows with optional filters."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conditions, params = [], []
            if active_only:
                conditions.append("is_active = 1")
            if tenant_id:
                conditions.append("tenant_id = ?")
                params.append(tenant_id)
            where = " AND ".join(conditions) if conditions else "1=1"
            rows = conn.execute(
                f"SELECT * FROM workflows WHERE {where} ORDER BY name", params,
            ).fetchall()
            conn.close()
            return [self._row_to_workflow(r) for r in rows]
        except Exception:
            return []

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow."""
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute("DELETE FROM workflows WHERE workflow_id = ?", (workflow_id,))
            conn.commit()
            conn.close()
            return cur.rowcount > 0
        except Exception:
            return False

    # ── Execution persistence ──────────────────────────────

    def persist_execution(self, execution: WorkflowExecution) -> None:
        """Persist a workflow execution."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO workflow_executions
                   (execution_id, workflow_id, current_step_index, status,
                    action_type, action_config, requested_by, step_results,
                    created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution.execution_id, execution.workflow_id,
                    execution.current_step_index, execution.status,
                    execution.action_type, json.dumps(execution.action_config),
                    execution.requested_by, json.dumps(execution.step_results),
                    execution.created_at, execution.completed_at,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("WorkflowDB: Persist execution failed: %s", exc)

    def update_execution(self, execution: WorkflowExecution) -> None:
        """Update a workflow execution."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """UPDATE workflow_executions SET
                   current_step_index=?, status=?, step_results=?, completed_at=?
                   WHERE execution_id=?""",
                (
                    execution.current_step_index, execution.status,
                    json.dumps(execution.step_results),
                    execution.completed_at, execution.execution_id,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("WorkflowDB: Update execution failed: %s", exc)

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get a workflow execution by ID."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            conn.close()
            if not row:
                return None
            return WorkflowExecution(
                execution_id=row["execution_id"],
                workflow_id=row["workflow_id"],
                current_step_index=row["current_step_index"],
                status=row["status"],
                action_type=row["action_type"] or "",
                action_config=json.loads(row["action_config"] or "{}"),
                requested_by=row["requested_by"] or 0,
                step_results=json.loads(row["step_results"] or "[]"),
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )
        except Exception:
            return None

    @staticmethod
    def _row_to_workflow(row: sqlite3.Row) -> WorkflowDefinition:
        """Convert a DB row to a WorkflowDefinition."""
        steps_data = json.loads(row["steps"])
        return WorkflowDefinition(
            workflow_id=row["workflow_id"],
            name=row["name"],
            description=row["description"] or "",
            steps=[WorkflowStep.from_dict(s) for s in steps_data],
            trigger_actions=json.loads(row["trigger_actions"]),
            is_active=bool(row["is_active"]),
            tenant_id=row["tenant_id"],
            created_at=row["created_at"],
        )


def get_builtin_workflows() -> List[WorkflowDefinition]:
    """Return the built-in workflow templates."""
    return [
        WorkflowDefinition(
            workflow_id="wf-financial-single",
            name="Aprobación Financiera Simple",
            description="Acciones financieras requieren aprobación de gerente",
            steps=[
                WorkflowStep(
                    step_type=WorkflowStepType.APPROVAL,
                    required_role="gerente",
                    name="Aprobación Gerente",
                    description="Gerente aprueba la acción financiera",
                    is_final=True,
                ),
            ],
            trigger_actions=["create_payment", "approve_financial", "refund"],
        ),
        WorkflowDefinition(
            workflow_id="wf-destructive-single",
            name="Aprobación Destructiva",
            description="Acciones destructivas requieren aprobación de admin",
            steps=[
                WorkflowStep(
                    step_type=WorkflowStepType.APPROVAL,
                    required_role="admin",
                    name="Aprobación Admin",
                    description="Admin aprueba la acción destructiva",
                    is_final=True,
                ),
            ],
            trigger_actions=["approve_destructive", "delete_record"],
        ),
        WorkflowDefinition(
            workflow_id="wf-system-change",
            name="Cambio de Sistema (2 pasos)",
            description="Cambios de sistema requieren notificación + aprobación",
            steps=[
                WorkflowStep(
                    step_type=WorkflowStepType.NOTIFICATION,
                    required_role="admin",
                    name="Notificar Admin",
                    description="Admin es notificado del cambio pendiente",
                ),
                WorkflowStep(
                    step_type=WorkflowStepType.APPROVAL,
                    required_role="admin",
                    name="Aprobación Admin",
                    description="Admin aprueba el cambio de sistema",
                    is_final=True,
                ),
            ],
            trigger_actions=["change_config", "manage_system"],
        ),
    ]
