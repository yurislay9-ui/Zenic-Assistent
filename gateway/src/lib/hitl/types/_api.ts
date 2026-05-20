// ─── Zenic-Agents v3 — HITL Type System: API ─────────────────────────
// Phase 5: API request/response types, statistics, compliance, and
//          Phase 5 enhancement record types (expiry, SLA, notification log)

import type {
  ApprovalType,
  ApprovalPriority,
  ApprovalRequestStatus,
  DecisionType,
  UndoType,
  CreateApprovalRequestInput,
} from "./_core";
import type {
  AttachEvidenceInput,
  ProvideJustificationInput,
} from "./_workflow";

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
  eventType: import("./_core").HitlEventType;
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

// ═══════════════════════════════════════════════════════════════════════════
// Phase 5 Enhancement Record Types
// ═══════════════════════════════════════════════════════════════════════════

/** Expiry record for auto-revert */
export interface ExpiryRecord {
  /** Request ID */
  requestId: string;
  /** When the request expires */
  expiresAt: string;
  /** Whether auto-revert is enabled */
  autoRevertEnabled: boolean;
  /** Compensating action for auto-revert (JSON) */
  revertAction: Record<string, unknown>;
  /** Minutes before expiry to notify */
  notificationSchedule: number[];
  /** Notifications sent so far */
  notificationsSent: Array<{ minutesBefore: number; sentAt: string }>;
  /** Status */
  status: "active" | "expired" | "reverted" | "cancelled";
  /** When reverted */
  revertedAt: string | null;
  /** Result of revert */
  revertResult: Record<string, unknown> | null;
  /** When created */
  createdAt: string;
  /** When updated */
  updatedAt: string;
}

/** Escalation SLA record */
export interface EscalationSLA {
  /** SLA ID */
  slaId: string;
  /** Request ID */
  requestId: string;
  /** Current escalation level (0-3) */
  currentLevel: number;
  /** Target role for this level */
  targetRole: string;
  /** When the SLA expires */
  slaDeadline: string;
  /** Whether the SLA was breached */
  breached: boolean;
  /** Whether auto-escalation occurred */
  autoEscalated: boolean;
  /** When escalated */
  escalatedAt: string | null;
  /** Why escalation happened */
  escalationReason: string;
  /** When created */
  createdAt: string;
  /** When updated */
  updatedAt: string;
}

/** Notification log record */
export interface NotificationLogRecord {
  /** Notification ID */
  notificationId: string;
  /** Request ID */
  requestId: string;
  /** Recipient user ID */
  recipientId: string;
  /** Channel */
  channel: string;
  /** Event type */
  event: string;
  /** Title */
  title: string;
  /** Body */
  body: string;
  /** Priority */
  priority: string;
  /** Status */
  status: "pending" | "sent" | "failed" | "delivered";
  /** Metadata */
  metadata: Record<string, unknown>;
  /** When sent */
  sentAt: string | null;
  /** When delivered */
  deliveredAt: string | null;
  /** When failed */
  failedAt: string | null;
  /** Error message */
  errorMessage: string | null;
  /** When created */
  createdAt: string;
}

/** Extended create approval request input with evidence and justification */
export interface ExtendedCreateApprovalRequestInput extends CreateApprovalRequestInput {
  /** Evidence to attach */
  evidence?: AttachEvidenceInput[];
  /** Pre-approval justification (optional at creation) */
  justification?: ProvideJustificationInput;
  /** Auto-revert on expiry configuration */
  autoRevertOnExpiry?: boolean;
  /** Compensating action for auto-revert */
  revertAction?: Record<string, unknown>;
  /** Expiry notification schedule (minutes before expiry) */
  expiryNotificationSchedule?: number[];
}
