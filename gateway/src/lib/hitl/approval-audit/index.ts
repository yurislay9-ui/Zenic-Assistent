// ─── Zenic-Agents v3 — HITL Approval Audit (barrel) ─────────────────

export {
  computeContentHash,
  recordAuditEvent,
  getAuditTrail,
  verifyAuditIntegrity,
  getApprovalTimeline,
} from "./_auditor";

export {
  exportComplianceRecord,
  batchExportComplianceRecords,
} from "./_persistence";
