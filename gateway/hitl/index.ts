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
