"""
Zenic-Agents Asistente - Approval Package (Phase 6.1 + C3)

Chain-of-approval system + configurable workflows for critical actions.

Components:
- ApprovalChain: Request/approve/reject approval requests with role-based authority
- WorkflowEngine: Multi-step approval workflows with configurable triggers
- AdaptiveApprovalEngine: Learns from past approvals to auto-approve safe actions
- RiskBasedApprovalRouter: Routes approval based on contextual risk score
- DelegationManager: Handles approver substitution when primary is unavailable
- BatchApprovalEngine: Approve/reject multiple similar actions at once
"""

from .chain import (
    ApprovalChain,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    ApprovalPriority,
    get_approval_chain,
    reset_approval_chain,
)

from .workflows import (
    WorkflowEngine,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowStepType,
    WorkflowExecution,
    get_workflow_engine,
    reset_workflow_engine,
)

from .adaptive import (
    AdaptiveApprovalRecord,
    AdaptiveApprovalEngine,
    get_adaptive_approval,
    reset_adaptive_approval,
)

from .risk_routing import (
    RiskLevel,
    RiskAssessment,
    RiskBasedApprovalRouter,
    get_risk_router,
    reset_risk_router,
)

from .delegation import (
    DelegationRule,
    DelegationRecord,
    DelegationManager,
    get_delegation_manager,
    reset_delegation_manager,
)

from .batch import (
    BatchRequest,
    BatchResult,
    BatchApprovalEngine,
    get_batch_approval,
    reset_batch_approval,
)

__all__ = [
    # Chain
    "ApprovalChain",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalStatus",
    "ApprovalPriority",
    "get_approval_chain",
    "reset_approval_chain",
    # Workflows
    "WorkflowEngine",
    "WorkflowDefinition",
    "WorkflowStep",
    "WorkflowStepType",
    "WorkflowExecution",
    "get_workflow_engine",
    "reset_workflow_engine",
    # Adaptive (C3)
    "AdaptiveApprovalRecord",
    "AdaptiveApprovalEngine",
    "get_adaptive_approval",
    "reset_adaptive_approval",
    # Risk Routing (C3)
    "RiskLevel",
    "RiskAssessment",
    "RiskBasedApprovalRouter",
    "get_risk_router",
    "reset_risk_router",
    # Delegation (C3)
    "DelegationRule",
    "DelegationRecord",
    "DelegationManager",
    "get_delegation_manager",
    "reset_delegation_manager",
    # Batch (C3)
    "BatchRequest",
    "BatchResult",
    "BatchApprovalEngine",
    "get_batch_approval",
    "reset_batch_approval",
]
