// ─── Zenic-Agents v3 — HITL Coordinator Types ──────────────────────────
// Phase 5: Result type interfaces for the HITL Coordinator facade.

import type {
  ApprovalRequest,
  ApprovalEvidence,
  ApprovalJustification,
  ExpiryRecord,
  EscalationSLA,
  ApprovalAuditRecord,
  ApprovalTimelineEvent,
  ApprovalDecision,
  UndoAction,
} from "../types";

/** Result of createFullRequest */
export interface CreateFullRequestResult {
  request: ApprovalRequest;
  evidence: ApprovalEvidence[];
  justification: ApprovalJustification | null;
  expiry: ExpiryRecord;
  sla: EscalationSLA;
}

/** Result of fullApprove */
export interface FullApproveResult {
  request: ApprovalRequest;
  justification: ApprovalJustification;
  executionResult?: {
    success: boolean;
    executionResult: Record<string, unknown>;
    snapshot: Record<string, unknown>;
  };
}

/** Result of fullReject */
export interface FullRejectResult {
  request: ApprovalRequest;
  justification: ApprovalJustification;
}

/** Result of fullUndo */
export interface FullUndoResult {
  undoAction: UndoAction;
  expiryCancelled: boolean;
}

/** Result of processExpired */
export interface ProcessExpiredResult {
  expired: ExpiryRecord[];
  reverted: Array<{ requestId: string; success: boolean }>;
}

/** Result of processSLABreaches */
export interface ProcessSLABreachesResult {
  breached: EscalationSLA[];
  escalated: EscalationSLA[];
}

/** Expiry notification item */
export interface ExpiryNotificationItem {
  requestId: string;
  minutesRemaining: number;
}

/** Result of getFullRequestDetails */
export interface FullRequestDetailsResult {
  request: ApprovalRequest | null;
  evidence: ApprovalEvidence[];
  justification: ApprovalJustification | null;
  expiry: ExpiryRecord | null;
  sla: EscalationSLA | null;
  auditTrail: ApprovalAuditRecord[];
  timeline: ApprovalTimelineEvent[];
  decisions: ApprovalDecision[];
}
