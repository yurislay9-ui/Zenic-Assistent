// ─── Zenic-Agents v3 — Human-in-the-Loop (HITL) Type System ────────────
// Phase 5: Rich Reversible Approval System
//
// Design Patterns:
//   - Value Object: Immutable approval request documents
//   - Strategy: ApprovalPolicyStrategy with pluggable quorum/unanimous/majority rules
//   - Chain of Responsibility: Escalation chain handlers
//   - Memento: Undo snapshots for reversible actions
//   - Observer: Notification listeners for approval events
//   - Singleton: ApprovalEngine, NotificationService

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

// ═══════════════════════════════════════════════════════════════════════════
// Notification Types
// ═══════════════════════════════════════════════════════════════════════════

/** In-app notification */
export interface HitlNotification {
  /** Notification ID */
  id: string;
  /** Target user ID */
  userId: string;
  /** Notification type */
  type: "approval_pending" | "approval_approved" | "approval_rejected" | "approval_delegated" | "approval_escalated" | "approval_expired" | "approval_undone" | "undo_available";
  /** Title */
  title: string;
  /** Message body */
  message: string;
  /** Related request ID */
  requestId: string;
  /** Priority */
  priority: NotificationPriority;
  /** Channel */
  channel: NotificationChannel;
  /** Whether read */
  isRead: boolean;
  /** When created */
  createdAt: string;
}

/** Notification subscription */
export interface NotificationSubscription {
  /** User ID */
  userId: string;
  /** Channels the user is subscribed to */
  channels: NotificationChannel[];
  /** Whether digest mode is enabled */
  digestMode: boolean;
  /** Digest interval in minutes */
  digestIntervalMinutes: number;
  /** Priority filter (only receive notifications >= this priority) */
  minPriority: NotificationPriority;
}

// ═══════════════════════════════════════════════════════════════════════════
// Compensating Action Registry (Memento Pattern)
// ═══════════════════════════════════════════════════════════════════════════

/** Compensating action descriptor */
export interface CompensatingActionDescriptor {
  /** Action type identifier */
  actionType: string;
  /** Description of what this compensating action does */
  description: string;
  /** Whether this action is truly reversible */
  isReversible: boolean;
  /** Reason if irreversible */
  irreversibilityReason?: string;
  /** Default undo window in ms */
  defaultUndoWindowMs: number;
  /** Function to generate undo payload from action payload */
  generateUndoPayload: (actionPayload: Record<string, unknown>) => Record<string, unknown>;
  /** Function to capture state snapshot before action */
  captureSnapshot: (actionPayload: Record<string, unknown>) => Promise<Record<string, unknown>>;
  /** Function to execute the undo */
  executeUndo: (undoPayload: Record<string, unknown>, snapshot: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

// ═══════════════════════════════════════════════════════════════════════════
// API Request/Response Types
// ═══════════════════════════════════════════════════════════════════════════

/** Approve request input */
export interface ApproveRequestInput {
  /** User ID of approver */
  decisionBy: string;
  /** Display name of approver */
  decisionByName: string;
  /** Approver's role */
  role: string;
  /** Approval comment */
  comment?: string;
  /** If approving on behalf of someone (delegated) */
  delegatedFrom?: string;
}

/** Reject request input */
export interface RejectRequestInput {
  /** User ID of rejecter */
  decisionBy: string;
  /** Display name of rejecter */
  decisionByName: string;
  /** Rejecter's role */
  role: string;
  /** Rejection reason (required) */
  comment: string;
}

/** Delegate request input */
export interface DelegateRequestInput {
  /** User ID delegating */
  fromUserId: string;
  /** Display name of delegator */
  fromUserName: string;
  /** User ID to delegate to */
  toUserId: string;
  /** Display name of delegate */
  toUserName: string;
  /** Reason for delegation */
  reason?: string;
  /** When the delegation expires */
  expiresAt?: string;
}

/** Escalate request input */
export interface EscalateRequestInput {
  /** User ID initiating escalation */
  fromUserId?: string;
  /** Target user ID */
  toUserId?: string;
  /** Target role for escalation */
  toRole: string;
  /** Reason for escalation */
  reason?: string;
}

/** Undo request input */
export interface UndoRequestInput {
  /** User ID initiating undo */
  undoBy: string;
  /** Display name of undo initiator */
  undoByName: string;
  /** Reason for undo */
  reason: string;
  /** Type of undo */
  undoType?: UndoType;
}

/** Create delegation rule input */
export interface CreateDelegationRuleInput {
  /** User ID delegating */
  fromUserId: string;
  /** User ID delegated to */
  toUserId: string;
  /** Display name of delegate */
  toUserName: string;
  /** Rule name */
  ruleName: string;
  /** Description */
  description?: string;
  /** Maximum delegation depth */
  maxDepth?: number;
  /** When the rule expires */
  expiresAt?: string;
}

/** List/query options for approval requests */
export interface ApprovalListOptions {
  /** Filter by status */
  status?: ApprovalRequestStatus | ApprovalRequestStatus[];
  /** Filter by priority */
  priority?: ApprovalPriority;
  /** Filter by requester */
  requesterId?: string;
  /** Filter by type */
  type?: ApprovalType;
  /** Filter by target resource */
  targetResource?: string;
  /** Page number (1-based) */
  page?: number;
  /** Page size */
  pageSize?: number;
  /** Sort field */
  sortBy?: "createdAt" | "updatedAt" | "priority" | "deadline";
  /** Sort direction */
  sortOrder?: "asc" | "desc";
}

/** Approval statistics */
export interface ApprovalStats {
  /** Total requests */
  total: number;
  /** By status */
  byStatus: Record<ApprovalRequestStatus, number>;
  /** By priority */
  byPriority: Record<ApprovalPriority, number>;
  /** By type */
  byType: Record<ApprovalType, number>;
  /** Average time to decision (ms) */
  avgTimeToDecision: number;
  /** Average time to execution (ms) */
  avgTimeToExecution: number;
  /** Undo rate (0-1) */
  undoRate: number;
  /** Auto-approve rate (0-1) */
  autoApproveRate: number;
  /** Delegation rate (0-1) */
  delegationRate: number;
  /** Escalation rate (0-1) */
  escalationRate: number;
}

/** Approval timeline event (for visualization) */
export interface ApprovalTimelineEvent {
  /** Event type */
  eventType: HitlEventType;
  /** Timestamp */
  timestamp: string;
  /** Actor */
  actorId: string;
  /** Actor name */
  actorName: string;
  /** Description */
  description: string;
  /** Additional details */
  details: Record<string, unknown>;
}

/** Compliance export record */
export interface ComplianceExportRecord {
  /** Request ID */
  requestId: string;
  /** Title */
  title: string;
  /** Type */
  type: ApprovalType;
  /** Status */
  status: ApprovalRequestStatus;
  /** Requester */
  requester: string;
  /** Approvers */
  approvers: Array<{
    name: string;
    role: string;
    decision: DecisionType;
    decidedAt: string;
    comment: string;
  }>;
  /** Delegations */
  delegations: Array<{
    from: string;
    to: string;
    reason: string;
    createdAt: string;
  }>;
  /** Escalations */
  escalations: Array<{
    fromLevel: number;
    toLevel: number;
    toRole: string;
    reason: string;
    createdAt: string;
  }>;
  /** Action execution */
  executedAt: string | null;
  /** Undo */
  undo: {
    executedAt: string | null;
    undoBy: string | null;
    reason: string | null;
  };
  /** Created at */
  createdAt: string;
  /** Timeline hash for integrity verification */
  integrityHash: string;
}
