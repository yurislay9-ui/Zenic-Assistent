// ─── Zenic-Agents v3 — Human-in-the-Loop (HITL) Barrel Export ────────
// Phase 5: Rich Reversible Approval System
// Public API — import anything from '@/lib/hitl'

// ─── Types ─────────────────────────────────────────────────────────────
export * from "./types";

// ─── Approval Engine ──────────────────────────────────────────────────
export {
  getApprovalEngine,
  resetApprovalEngine,
  evaluateAutoApproveRules,
  isApprovalPolicySatisfied,
} from "./approval-engine";

// ─── Reversible Action System ─────────────────────────────────────────
export {
  getReversibleActionService,
  getCompensatingActionRegistry,
  resetReversibleActionService,
} from "./reversible-action";

// ─── Delegation & Escalation ──────────────────────────────────────────
export {
  getDelegationService,
  getEscalationService,
  resetDelegationService,
  resetEscalationService,
} from "./delegation";

// ─── Approval Audit Trail ─────────────────────────────────────────────
export {
  recordAuditEvent,
  getAuditTrail,
  verifyAuditIntegrity,
  getApprovalTimeline,
  exportComplianceRecord,
  batchExportComplianceRecords,
} from "./approval-audit";

// ─── Notification System ──────────────────────────────────────────────
export {
  getNotificationService,
  resetNotificationService,
  notifyApprovalEvent,
} from "./notifications";

// ─── Phase 5 Enhancements ──────────────────────────────────────────
export {
  getEvidenceService,
  resetEvidenceService,
} from "./evidence-service";

export {
  getJustificationService,
  resetJustificationService,
} from "./justification-service";

export {
  getExpiryService,
  resetExpiryService,
} from "./expiry-service";

export {
  getSLAService,
  resetSLAService,
} from "./sla-service";

export {
  getNotificationLogService,
  resetNotificationLogService,
} from "./notification-log-service";

// ─── Phase 5 Coordinator & Pipeline ─────────────────────────────────
export {
  getHITLCoordinator,
  resetHITLCoordinator,
  getHITLProcessingService,
  resetHITLProcessingService,
} from "./hitl-coordinator";

export type {
  CreateFullRequestResult,
  FullApproveResult,
  FullRejectResult,
  FullUndoResult,
  ProcessExpiredResult,
  ProcessSLABreachesResult,
  ExpiryNotificationItem,
  FullRequestDetailsResult,
} from "./hitl-coordinator";

export {
  getPipelineIntegration,
  resetPipelineIntegration,
} from "./pipeline-integration";

// Re-export pipeline integration types for convenience
export type {
  SafetyGateVerdict,
  PolicyApprovalRequirement,
} from "./pipeline-integration";
