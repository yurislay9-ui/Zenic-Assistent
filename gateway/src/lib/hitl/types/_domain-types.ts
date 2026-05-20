// ─── Zenic-Agents v3 — HITL Policy & Core Domain Types ────────────────
// Split from types.ts — policy types, approval request, decision, delegation, escalation, undo, audit

import type { ApprovalPolicyMode, ApprovalPriority, ApprovalType, ApprovalRequestStatus, DecisionType, UndoType, UndoStatus, HitlEventType } from "./_enums";

// ─── Approval Policy Types (Strategy Pattern) ──────────────────────────

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

// ─── Core Domain Objects ───────────────────────────────────────────────

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

/** Approval decision */
export interface ApprovalDecision {
  /** Decision ID */
  id: string;
  /** Request ID this decision belongs to */
  requestId: string;
  /** Decision type */
  decision: DecisionType;
  /** User ID who made the decision */
  decisionBy: string;
  /** Display name of decision maker */
  decisionByName: string;
  /** Role of the decision maker */
  role: string;
  /** Comment/feedback */
  comment: string;
  /** If this decision was delegated from someone else */
  delegatedFrom: string | null;
  /** When the decision was made */
  decidedAt: string;
}

/** Delegation record */
export interface Delegation {
  /** Delegation ID */
  id: string;
  /** Request ID */
  requestId: string;
  /** User ID who delegated */
  fromUserId: string;
  /** Display name of delegator */
  fromUserName: string;
  /** User ID delegated to */
  toUserId: string;
  /** Display name of delegate */
  toUserName: string;
  /** Reason for delegation */
  reason: string;
  /** When the delegation expires */
  expiresAt: string | null;
  /** Whether this delegation is still active */
  isActive: boolean;
  /** When the delegation was created */
  createdAt: string;
}

/** Delegation rule (standing delegation) */
export interface DelegationRule {
  /** Rule ID */
  id: string;
  /** User ID who delegates */
  fromUserId: string;
  /** User ID delegated to */
  toUserId: string;
  /** Display name of delegate */
  toUserName: string;
  /** Rule name */
  ruleName: string;
  /** Description */
  description: string;
  /** Whether active */
  isActive: boolean;
  /** Maximum delegation chain depth */
  maxDepth: number;
  /** When the rule expires */
  expiresAt: string | null;
  /** Creation timestamp */
  createdAt: string;
  /** Last update timestamp */
  updatedAt: string;
}

/** Escalation record */
export interface Escalation {
  /** Escalation ID */
  id: string;
  /** Request ID */
  requestId: string;
  /** Escalation source level */
  fromLevel: number;
  /** Escalation target level */
  toLevel: number;
  /** User ID who was the approver at source level */
  fromUserId: string | null;
  /** User ID at target level */
  toUserId: string | null;
  /** Target role for escalation */
  toRole: string;
  /** Reason for escalation */
  reason: string;
  /** Whether this was an automatic escalation */
  autoEscalated: boolean;
  /** When the escalation was created */
  createdAt: string;
}

/** Undo action record */
export interface UndoAction {
  /** Undo action ID */
  id: string;
  /** Request ID */
  requestId: string;
  /** Type of undo */
  undoType: UndoType;
  /** User ID who initiated the undo */
  undoBy: string;
  /** Display name of undo initiator */
  undoByName: string;
  /** Reason for undo */
  reason: string;
  /** State snapshot before the action was executed */
  snapshotBefore: Record<string, unknown>;
  /** Undo action parameters */
  undoPayload: Record<string, unknown>;
  /** Result of undo execution */
  undoResult: Record<string, unknown> | null;
  /** Undo status */
  status: UndoStatus;
  /** When the undo was executed */
  executedAt: string | null;
  /** When the undo record was created */
  createdAt: string;
}

/** Approval audit record */
export interface ApprovalAuditRecord {
  /** Audit record ID */
  id: string;
  /** Request ID */
  requestId: string;
  /** Event type */
  eventType: HitlEventType;
  /** User ID of the actor */
  actorId: string;
  /** Display name of the actor */
  actorName: string;
  /** Event-specific details */
  details: Record<string, unknown>;
  /** SHA-256 content hash for integrity */
  contentHash: string;
  /** Previous record hash for Merkle chain */
  previousHash: string | null;
  /** Event timestamp */
  timestamp: string;
}
