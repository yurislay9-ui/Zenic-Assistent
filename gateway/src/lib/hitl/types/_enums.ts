// ─── Zenic-Agents v3 — HITL Enums & Constants ────────────────────────
// Split from types.ts — enum-like const objects and type aliases

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

/** Approval policy mode */
export const ApprovalPolicyMode = {
  SINGLE: "single",         // Any single approver suffices
  UNANIMOUS: "unanimous",   // All required approvers must approve
  MAJORITY: "majority",     // More than half of required approvers
  QUORUM: "quorum",         // Minimum number of approvers
  AUTO_APPROVE: "auto_approve", // Automatic approval if conditions met
} as const;
export type ApprovalPolicyMode = (typeof ApprovalPolicyMode)[keyof typeof ApprovalPolicyMode];

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
