// ─── Zenic-Agents v3 — HITL API Request/Response Types ────────────────
// Split from types.ts — API input types, list options, stats, timeline, compliance export

import type { ApprovalPriority, ApprovalType, ApprovalRequestStatus, DecisionType, HitlEventType, UndoType } from "./_enums";

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
