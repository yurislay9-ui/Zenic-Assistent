"""
Zenic-Agents Asistente - Approval Package (Phase 6.1 + C3 + Phase 5)

Chain-of-approval system + configurable workflows for critical actions.

Components:
- ApprovalChain: Request/approve/reject approval requests with role-based authority
- WorkflowEngine: Multi-step approval workflows with configurable triggers
- AdaptiveApprovalEngine: Learns from past approvals to auto-approve safe actions
- RiskBasedApprovalRouter: Routes approval based on contextual risk score
- DelegationManager: Handles approver substitution when primary is unavailable
- BatchApprovalEngine: Approve/reject multiple similar actions at once
- EvidenceManager: Attach immutable evidence to approval requests (Phase 5)
- JustificationManager: Mandatory justification for approve/reject (Phase 5)
- ExpiryManager: Expiration with auto-revert (Phase 5)
- RollbackManager: SAGA-inspired compensation/rollback (Phase 5)
- NotificationDispatcher: Multi-channel approval notifications (Phase 5)
- EscalationManager: SLA-based escalation (Phase 5)
- ApprovalAuditMerkle: Merkle-chain audit trail (Phase 5)
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

from .evidence import (
    EvidenceType,
    ApprovalEvidence,
    EvidenceManager,
    get_evidence_manager,
    reset_evidence_manager,
)

from .justification import (
    JustificationRequirement,
    ApprovalJustification,
    JustificationManager,
    get_justification_manager,
    reset_justification_manager,
)

from .expiry import (
    ExpiryConfig,
    ExpiryRecord,
    ExpiryManager,
    get_expiry_manager,
    reset_expiry_manager,
)

from .rollback import (
    RollbackStatus,
    RollbackTrigger,
    CompensationAction,
    RollbackRecord,
    RollbackManager,
    get_rollback_manager,
    reset_rollback_manager,
)

from .notification import (
    NotificationChannel,
    NotificationPriority,
    NotificationEvent,
    NotificationMessage,
    ChannelConfig,
    NotificationDispatcher,
    get_notification_dispatcher,
    reset_notification_dispatcher,
)

from .escalation import (
    EscalationLevel,
    SLAPolicy,
    EscalationSLA,
    EscalationManager,
    get_escalation_manager,
    reset_escalation_manager,
)

from .audit_merkle import (
    AuditEventType,
    AuditRecord,
    MerkleProof,
    GENESIS_HASH,
    ApprovalAuditMerkle,
    get_approval_audit_merkle,
    reset_approval_audit_merkle,
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
    # Evidence (Phase 5)
    "EvidenceType",
    "ApprovalEvidence",
    "EvidenceManager",
    "get_evidence_manager",
    "reset_evidence_manager",
    # Justification (Phase 5)
    "JustificationRequirement",
    "ApprovalJustification",
    "JustificationManager",
    "get_justification_manager",
    "reset_justification_manager",
    # Expiry (Phase 5)
    "ExpiryConfig",
    "ExpiryRecord",
    "ExpiryManager",
    "get_expiry_manager",
    "reset_expiry_manager",
    # Rollback (Phase 5)
    "RollbackStatus",
    "RollbackTrigger",
    "CompensationAction",
    "RollbackRecord",
    "RollbackManager",
    "get_rollback_manager",
    "reset_rollback_manager",
    # Notification (Phase 5)
    "NotificationChannel",
    "NotificationPriority",
    "NotificationEvent",
    "NotificationMessage",
    "ChannelConfig",
    "NotificationDispatcher",
    "get_notification_dispatcher",
    "reset_notification_dispatcher",
    # Escalation (Phase 5)
    "EscalationLevel",
    "SLAPolicy",
    "EscalationSLA",
    "EscalationManager",
    "get_escalation_manager",
    "reset_escalation_manager",
    # Audit Merkle (Phase 5)
    "AuditEventType",
    "AuditRecord",
    "MerkleProof",
    "GENESIS_HASH",
    "ApprovalAuditMerkle",
    "get_approval_audit_merkle",
    "reset_approval_audit_merkle",
]
