// ─── Zenic-Agents v3 — HITL Approval Engine: Barrel Export ───────────
// Re-exports everything so that `import { ... } from "./approval-engine"`
// continues to work unchanged.

export { getApprovalEngine, resetApprovalEngine } from "./_engine";
export { evaluateAutoApproveRules, isApprovalPolicySatisfied } from "./_routing";
