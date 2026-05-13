"""
Zenic-Agents Asistente - Approval Workflows (Phase 6.1c)

Configurable multi-step approval workflows. Each workflow defines
a sequence of approval steps with specific role requirements.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .chain import ApprovalChain, ApprovalPriority, get_approval_chain

logger = logging.getLogger(__name__)


class WorkflowStepType(str, Enum):
    """Type of workflow step."""
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    CONDITION = "condition"
    DELAY = "delay"


@dataclass
class WorkflowStep:
    """A single step in an approval workflow."""
    step_id: str = ""
    step_type: WorkflowStepType = WorkflowStepType.APPROVAL
    required_role: str = "gerente"
    action: str = ""
    name: str = ""
    description: str = ""
    timeout_hours: int = 24
    is_final: bool = False
    condition_expr: str = ""

    def __post_init__(self) -> None:
        if not self.step_id:
            self.step_id = f"step-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id, "step_type": self.step_type.value,
            "required_role": self.required_role, "action": self.action,
            "name": self.name, "description": self.description,
            "timeout_hours": self.timeout_hours, "is_final": self.is_final,
            "condition_expr": self.condition_expr,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=data.get("step_id", ""),
            step_type=WorkflowStepType(data.get("step_type", "approval")),
            required_role=data.get("required_role", "gerente"),
            action=data.get("action", ""), name=data.get("name", ""),
            description=data.get("description", ""),
            timeout_hours=data.get("timeout_hours", 24),
            is_final=data.get("is_final", False),
            condition_expr=data.get("condition_expr", ""),
        )


@dataclass
class WorkflowDefinition:
    """Definition of an approval workflow."""
    workflow_id: str = ""
    name: str = ""
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    trigger_actions: List[str] = field(default_factory=list)
    is_active: bool = True
    tenant_id: str = "__anonymous__"
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.workflow_id:
            self.workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id, "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "trigger_actions": self.trigger_actions,
            "is_active": self.is_active, "tenant_id": self.tenant_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowDefinition":
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            workflow_id=data.get("workflow_id", ""), name=data.get("name", ""),
            description=data.get("description", ""), steps=steps,
            trigger_actions=data.get("trigger_actions", []),
            is_active=data.get("is_active", True),
            tenant_id=data.get("tenant_id", "__anonymous__"),
            created_at=data.get("created_at", ""),
        )


@dataclass
class WorkflowExecution:
    """Runtime state of a workflow execution."""
    execution_id: str = ""
    workflow_id: str = ""
    current_step_index: int = 0
    status: str = "in_progress"
    action_type: str = ""
    action_config: Dict[str, Any] = field(default_factory=dict)
    requested_by: int = 0
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.execution_id:
            self.execution_id = f"wfx-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class WorkflowEngine:
    """Engine for managing and executing approval workflows.

    Uses workflow_parts/persistence.py for database operations.
    """

    def __init__(self, db_path: str = "approval_workflows.sqlite") -> None:
        self._lock = threading.RLock()
        self._approval_chain = get_approval_chain()

        from .workflow_parts.persistence import WorkflowDB, get_builtin_workflows
        self._db = WorkflowDB(db_path)
        self._ensure_builtin_workflows(get_builtin_workflows())

    def _ensure_builtin_workflows(self, builtins: List[WorkflowDefinition]) -> None:
        """Create built-in workflows if they don't exist."""
        for wf in builtins:
            existing = self._db.get_workflow(wf.workflow_id)
            if not existing:
                self._db.create_workflow(wf)

    # ── CRUD ───────────────────────────────────────────────

    def create_workflow(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        """Create a new workflow definition."""
        self._db.create_workflow(workflow)
        logger.info("WorkflowEngine: Created workflow '%s'", workflow.name)
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get a workflow by ID."""
        return self._db.get_workflow(workflow_id)

    def list_workflows(
        self, tenant_id: Optional[str] = None, active_only: bool = True,
    ) -> List[WorkflowDefinition]:
        """List all workflows, optionally filtered."""
        return self._db.list_workflows(tenant_id=tenant_id, active_only=active_only)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow definition."""
        return self._db.delete_workflow(workflow_id)

    # ── Execution ──────────────────────────────────────────

    def trigger_workflow(
        self,
        action_type: str,
        action_config: Dict[str, Any],
        requested_by: int,
        tenant_id: str = "__anonymous__",
    ) -> Optional[WorkflowExecution]:
        """Find and start a workflow for the given action."""
        workflow = self._find_workflow_for_action(action_type, tenant_id)
        if not workflow:
            return None

        execution = WorkflowExecution(
            workflow_id=workflow.workflow_id,
            action_type=action_type,
            action_config=action_config,
            requested_by=requested_by,
        )

        self._db.persist_execution(execution)
        self._execute_step(execution, workflow, 0)

        logger.info(
            "WorkflowEngine: Triggered '%s' for '%s' (exec %s)",
            workflow.name, action_type, execution.execution_id,
        )
        return execution

    def advance_step(
        self,
        execution_id: str,
        approver_id: int,
        approver_role: str,
        approved: bool = True,
        notes: str = "",
    ) -> Optional[WorkflowExecution]:
        """Advance a workflow execution to the next step."""
        execution = self._db.get_execution(execution_id)
        if not execution:
            return None

        workflow = self.get_workflow(execution.workflow_id)
        if not workflow:
            return None

        result = {
            "step_index": execution.current_step_index,
            "approver_id": approver_id, "approver_role": approver_role,
            "approved": approved, "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        execution.step_results.append(result)

        if not approved:
            execution.status = "rejected"
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self._db.update_execution(execution)
            return execution

        next_index = execution.current_step_index + 1
        if next_index >= len(workflow.steps):
            execution.status = "completed"
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            execution.current_step_index = next_index
        else:
            execution.current_step_index = next_index
            self._execute_step(execution, workflow, next_index)

        self._db.update_execution(execution)
        return execution

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get a workflow execution by ID."""
        return self._db.get_execution(execution_id)

    # ── Private helpers ────────────────────────────────────

    def _find_workflow_for_action(
        self, action_type: str, tenant_id: str,
    ) -> Optional[WorkflowDefinition]:
        """Find a workflow that handles the given action type."""
        workflows = self.list_workflows(tenant_id=tenant_id, active_only=True)
        if tenant_id != "__anonymous__":
            workflows.extend(self.list_workflows(tenant_id="__anonymous__", active_only=True))

        for wf in workflows:
            if action_type in wf.trigger_actions:
                return wf
        return None

    def _execute_step(
        self, execution: WorkflowExecution, workflow: WorkflowDefinition, step_index: int,
    ) -> None:
        """Execute a workflow step."""
        if step_index >= len(workflow.steps):
            return

        step = workflow.steps[step_index]
        execution.current_step_index = step_index

        if step.step_type == WorkflowStepType.APPROVAL:
            self._approval_chain.create_request(
                action_type=execution.action_type,
                action_config=execution.action_config,
                requested_by=execution.requested_by,
                required_role=step.required_role,
                timeout_hours=step.timeout_hours,
            )
        elif step.step_type == WorkflowStepType.NOTIFICATION:
            logger.info(
                "WorkflowEngine: Notification '%s' sent (workflow %s)",
                step.name, workflow.workflow_id,
            )

    # ── Smart Approval Integration (Phase C3) ─────────────

    def trigger_workflow_with_risk(
        self,
        action_type: str,
        action_config: Dict[str, Any],
        requested_by: int,
        tenant_id: str = "__anonymous__",
    ) -> Optional[WorkflowExecution]:
        """Trigger a workflow with risk-based routing.
        
        Phase C3: Uses RiskBasedApprovalRouter to determine required role
        for each approval step.
        """
        execution = self.trigger_workflow(
            action_type, action_config, requested_by, tenant_id,
        )
        if execution is None:
            return None
        
        # Adjust approval steps based on risk
        workflow = self.get_workflow(execution.workflow_id)
        if workflow:
            try:
                from .risk_routing import get_risk_router
                router = get_risk_router()
                assessment = router.assess_risk(action_type, action_config, {})
                for step in workflow.steps:
                    if step.step_type == WorkflowStepType.APPROVAL:
                        if assessment.recommended_role:
                            step.required_role = assessment.recommended_role
            except Exception:
                pass
        
        return execution

    def check_delegations(self) -> List[Dict[str, Any]]:
        """Check for pending approvals that need delegation.
        
        Phase C3: Integration with DelegationManager.
        Returns list of delegated approval records.
        """
        delegated = []
        try:
            from .delegation import get_delegation_manager
            dm = get_delegation_manager()
            pending = self._approval_chain.list_pending()
            for request in pending:
                delegate_id = dm.auto_delegate_pending(
                    request.request_id, timeout_hours=2,
                )
                if delegate_id:
                    delegated.append({
                        "request_id": request.request_id,
                        "original_approver": request.requested_by,
                        "delegated_to": delegate_id,
                    })
        except Exception:
            pass
        return delegated


# ── Singleton ─────────────────────────────────────────────

_workflow_engine_instance: Optional[WorkflowEngine] = None
_workflow_engine_lock = threading.Lock()


def get_workflow_engine(db_path: str = "approval_workflows.sqlite") -> WorkflowEngine:
    """Get or create the global WorkflowEngine instance."""
    global _workflow_engine_instance
    with _workflow_engine_lock:
        if _workflow_engine_instance is None:
            _workflow_engine_instance = WorkflowEngine(db_path=db_path)
        return _workflow_engine_instance


def reset_workflow_engine() -> None:
    """Reset the global WorkflowEngine (for testing)."""
    global _workflow_engine_instance
    _workflow_engine_instance = None
