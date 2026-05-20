// ─── Zenic-Agents v3 — HITL Type System: Workflow ────────────────────
// Phase 5: Decision, delegation, escalation, undo, notification, and
//          compensating action types
//
// Design Patterns:
//   - Chain of Responsibility: Escalation chain handlers
//   - Memento: Undo snapshots for reversible actions
//   - Observer: Notification listeners for approval events

import type {
  DecisionType,
  UndoType,
  UndoStatus,
  HitlEventType,
  NotificationChannel,
  NotificationPriority,
} from "./_core";

// ═══════════════════════════════════════════════════════════════════════════
// Decision & Workflow Records
// ═══════════════════════════════════════════════════════════════════════════

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
// Phase 5 Enhancements: Evidence & Justification
// ═══════════════════════════════════════════════════════════════════════════

/** Evidence type for approval attachments */
export const EvidenceType = {
  SCREENSHOT: "screenshot",
  LOG: "log",
  DATA_SNAPSHOT: "data_snapshot",
  POLICY_RESULT: "policy_result",
  AUDIT_RECORD: "audit_record",
  CUSTOM: "custom",
} as const;
export type EvidenceType = (typeof EvidenceType)[keyof typeof EvidenceType];

/** Evidence attached to an approval request */
export interface ApprovalEvidence {
  /** Evidence ID */
  evidenceId: string;
  /** Request ID */
  requestId: string;
  /** Type of evidence */
  evidenceType: EvidenceType;
  /** Evidence content (JSON) */
  content: Record<string, unknown>;
  /** SHA-256 hash for immutability */
  contentHash: string;
  /** Who/what provided the evidence */
  source: string;
  /** Description */
  description: string;
  /** When created */
  createdAt: string;
}

/** Attach evidence input */
export interface AttachEvidenceInput {
  /** Type of evidence */
  evidenceType: EvidenceType;
  /** Evidence content */
  content: Record<string, unknown>;
  /** Who/what provided the evidence */
  source: string;
  /** Description */
  description?: string;
}

/** Justification for approval/rejection */
export interface ApprovalJustification {
  /** Justification ID */
  justificationId: string;
  /** Request ID */
  requestId: string;
  /** Decision ID (if tied to a specific decision) */
  decisionId: string | null;
  /** Mandatory reason */
  reason: string;
  /** Risk acknowledgment */
  riskAcknowledgment: boolean;
  /** Compliance check */
  complianceCheck: boolean;
  /** Business justification */
  businessJustification: string;
  /** User ID who provided justification */
  createdBy: string;
  /** Display name */
  createdByName: string;
  /** SHA-256 hash for immutability */
  contentHash: string;
  /** When created */
  createdAt: string;
}

/** Provide justification input */
export interface ProvideJustificationInput {
  /** Mandatory reason (min 20 chars for critical/emergency) */
  reason: string;
  /** Risk acknowledgment */
  riskAcknowledgment: boolean;
  /** Compliance check */
  complianceCheck: boolean;
  /** Business justification */
  businessJustification?: string;
  /** User ID */
  createdBy: string;
  /** Display name */
  createdByName: string;
  /** Decision ID (if tied to a specific decision) */
  decisionId?: string;
}
