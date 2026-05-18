// ─── Zenic-Agents v3 — HITL Type System: Core ────────────────────────
// Phase 5: Core enums, constants, policy types, and base domain objects
//
// Design Patterns:
//   - Value Object: Immutable approval request documents
//   - Strategy: ApprovalPolicyStrategy with pluggable quorum/unanimous/majority rules

// ═══════════════════════════════════════════════════════════════════════════
// Core Enums & Constants
// ═══════════════════════════════════════════════════════════════════════════

/** Approval request status lifecycle */
export const ApprovalRequestStatus = {
  PENDING: "pending",
  APPROVED: "approved",
  REJECTED: "rejected",
  DELEGATED: "delegated",
  ESCALATED: "escalated",
  EXPIRED: "expired",
  UNDONE: "undone",
  IRREVERSIBLE: "irreversible",
  CANCELLED: "cancelled",
} as const;
export type ApprovalRequestStatus = (typeof ApprovalRequestStatus)[keyof typeof ApprovalRequestStatus];

/** Priority levels for approval requests */
export const ApprovalPriority = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
  EMERGENCY: "emergency",
} as const;
export type ApprovalPriority = (typeof ApprovalPriority)[keyof typeof ApprovalPriority];

/** Types of actions requiring approval */
export const ApprovalType = {
  ACTION_APPROVAL: "action_approval",
  POLICY_CHANGE: "policy_change",
  DEPLOYMENT: "deployment",
  DATA_ACCESS: "data_access",
  CONFIGURATION: "configuration",
  FINANCIAL: "financial",
  SECURITY: "security",
} as const;
export type ApprovalType = (typeof ApprovalType)[keyof typeof ApprovalType];

/** Decision types for approval */
export const DecisionType = {
  APPROVED: "approved",
  REJECTED: "rejected",
} as const;
export type DecisionType = (typeof DecisionType)[keyof typeof DecisionType];

/** Escalation level */
export const EscalationLevel = {
  L0: 0, // Initial — direct approver
  L1: 1, // Team lead / manager
  L2: 2, // Director / VP
  L3: 3, // C-suite / emergency
} as const;

/** Undo action types */
export const UndoType = {
  FULL_UNDO: "full_undo",
  PARTIAL_UNDO: "partial_undo",
  COMPENSATING_ACTION: "compensating_action",
} as const;
export type UndoType = (typeof UndoType)[keyof typeof UndoType];

/** Undo action status */
export const UndoStatus = {
  PENDING: "pending",
  EXECUTED: "executed",
  FAILED: "failed",
  SKIPPED: "skipped",
} as const;
export type UndoStatus = (typeof UndoStatus)[keyof typeof UndoStatus];

/** Audit event types for HITL */
export const HitlEventType = {
  CREATED: "created",
  APPROVED: "approved",
  REJECTED: "rejected",
  DELEGATED: "delegated",
  ESCALATED: "escalated",
  EXECUTED: "executed",
  UNDONE: "undone",
  EXPIRED: "expired",
  CANCELLED: "cancelled",
} as const;
export type HitlEventType = (typeof HitlEventType)[keyof typeof HitlEventType];

/** Notification channel types */
export const NotificationChannel = {
  IN_APP: "in_app",
  EMAIL: "email",
  WEBHOOK: "webhook",
} as const;
export type NotificationChannel = (typeof NotificationChannel)[keyof typeof NotificationChannel];

/** Notification priority */
export const NotificationPriority = {
  LOW: "low",
  NORMAL: "normal",
  HIGH: "high",
  URGENT: "urgent",
} as const;
export type NotificationPriority = (typeof NotificationPriority)[keyof typeof NotificationPriority];

// ═══════════════════════════════════════════════════════════════════════════
// Approval Policy Types (Strategy Pattern)
// ═══════════════════════════════════════════════════════════════════════════

/** Approval policy mode */
export const ApprovalPolicyMode = {
  SINGLE: "single",         // Any single approver suffices
  UNANIMOUS: "unanimous",   // All required approvers must approve
  MAJORITY: "majority",     // More than half of required approvers
  QUORUM: "quorum",         // Minimum number of approvers
  AUTO_APPROVE: "auto_approve", // Automatic approval if conditions met
} as const;
export type ApprovalPolicyMode = (typeof ApprovalPolicyMode)[keyof typeof ApprovalPolicyMode];

/** Approval policy definition */
export interface ApprovalPolicy {
  /** Policy mode */
  mode: ApprovalPolicyMode;
  /** Minimum approvals needed (for quorum mode) */
  quorum?: number;
  /** Required roles that must approve */
  requiredRoles?: string[];
  /** Auto-approve rules */
  autoApproveRules?: AutoApproveRule[];
  /** Maximum time (ms) before auto-escalation */
  escalationTimeoutMs?: number;
  /** Escalation target role on timeout */
  escalationTargetRole?: string;
  /** Whether actions under this policy are reversible */
  defaultReversible?: boolean;
  /** Undo window in ms (null = unlimited) */
  undoWindowMs?: number;
}

/** Auto-approve rule for HITL */
export interface AutoApproveRule {
  /** Rule name */
  name: string;
  /** Whether the rule is enabled */
  enabled: boolean;
  /** Condition to match */
  condition: AutoApproveCondition;
  /** Maximum risk score for auto-approve */
  maxRiskScore?: number;
}

/** Auto-approve conditions */
export interface AutoApproveCondition {
  /** Priority levels eligible for auto-approve */
  allowedPriorities?: ApprovalPriority[];
  /** Maximum number of affected resources */
  maxAffectedResources?: number;
  /** Action types that can be auto-approved */
  allowedActionTypes?: ApprovalType[];
  /** Tags that must match */
  requiredTags?: string[];
  /** Maximum approval amount (for financial) */
  maxAmount?: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// Core Domain Objects
// ═══════════════════════════════════════════════════════════════════════════

/** Create approval request input */
export interface CreateApprovalRequestInput {
  /** Request title */
  title: string;
  /** Detailed description */
  description: string;
  /** Type of approval */
  type: ApprovalType;
  /** Priority level */
  priority?: ApprovalPriority;
  /** User ID of the requester */
  requesterId: string;
  /** Requester display name */
  requesterName: string;
  /** Target resource being affected */
  targetResource: string;
  /** Action being requested on the resource */
  targetAction: string;
  /** Action parameters (JSON-serializable) */
  actionPayload?: Record<string, unknown>;
  /** Compensating action parameters for undo */
  undoPayload?: Record<string, unknown>;
  /** Whether this action is reversible */
  isReversible?: boolean;
  /** Undo window in ms */
  undoWindowMs?: number;
  /** When the request expires */
  deadline?: string;
  /** Number of required approvals */
  requiredApprovals?: number;
  /** Approval policy configuration */
  approvalPolicy?: ApprovalPolicy;
  /** Parent request ID (for multi-level chains) */
  parentId?: string;
  /** Tags for categorization */
  tags?: string[];
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/** Approval request (full domain object) */
export interface ApprovalRequest {
  /** Database ID */
  id: string;
  /** Business request ID */
  requestId: string;
  /** Title */
  title: string;
  /** Description */
  description: string;
  /** Type */
  type: ApprovalType;
  /** Current status */
  status: ApprovalRequestStatus;
  /** Priority */
  priority: ApprovalPriority;
  /** Requester user ID */
  requesterId: string;
  /** Requester display name */
  requesterName: string;
  /** Target resource */
  targetResource: string;
  /** Target action */
  targetAction: string;
  /** Action payload (JSON) */
  actionPayload: Record<string, unknown>;
  /** Undo payload (JSON) */
  undoPayload: Record<string, unknown>;
  /** Whether reversible */
  isReversible: boolean;
  /** When the undo window expires */
  undoDeadline: string | null;
  /** When the undo was executed */
  undoExecutedAt: string | null;
  /** When the approved action was executed */
  executedAt: string | null;
  /** Result of the executed action */
  executionResult: Record<string, unknown> | null;
  /** Required approvals count */
  requiredApprovals: number;
  /** Current approvals count */
  currentApprovals: number;
  /** Approval policy */
  approvalPolicy: ApprovalPolicy;
  /** When the request expires */
  deadline: string | null;
  /** Current escalation level */
  escalationLevel: number;
  /** Parent request ID */
  parentId: string | null;
  /** Tags */
  tags: string[];
  /** Additional metadata */
  metadata: Record<string, unknown>;
  /** Creation timestamp */
  createdAt: string;
  /** Last update timestamp */
  updatedAt: string;
}
