// ─── Zenic-Agents v3 — HITL Notification & Phase 5 Types ──────────────
// Split from types.ts — notification types, compensating actions, evidence, justification, expiry, SLA

import type { NotificationChannel, NotificationPriority, EvidenceType, ApprovalType, ApprovalRequestStatus } from "./_enums";
import type { CreateApprovalRequestInput } from "./_domain-types";

// ─── Notification Types ────────────────────────────────────────────────

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

// ─── Compensating Action Registry (Memento Pattern) ────────────────────

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

// ─── Phase 5: Evidence Types ───────────────────────────────────────────

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

// ─── Phase 5: Justification Types ──────────────────────────────────────

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

// ─── Phase 5: Expiry Types ─────────────────────────────────────────────

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
