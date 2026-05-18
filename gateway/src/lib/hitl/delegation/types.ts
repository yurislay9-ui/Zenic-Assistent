// ─── Zenic-Agents v3 — HITL Delegation Types ─────────────────────────
// Phase 5: Re-exported types and escalation level configuration.

// Re-export shared types used by this module
export type {
  DelegateRequestInput,
  EscalateRequestInput,
  Delegation,
  DelegationRule,
  CreateDelegationRuleInput,
  Escalation,
} from "../types";

export {
  ApprovalRequestStatus,
  HitlEventType,
} from "../types";

// ═══════════════════════════════════════════════════════════════════════════
// Escalation Level Configuration
// ═══════════════════════════════════════════════════════════════════════════

/** Escalation level configuration */
export interface EscalationLevelConfig {
  level: number;
  role: string;
  timeoutMs: number;
}

export const DEFAULT_ESCALATION_CHAIN: EscalationLevelConfig[] = [
  { level: 0, role: "reviewer", timeoutMs: 0 },           // Direct approver
  { level: 1, role: "team_lead", timeoutMs: 3600000 },    // 1 hour
  { level: 2, role: "director", timeoutMs: 7200000 },     // 2 hours
  { level: 3, role: "c_suite", timeoutMs: 14400000 },     // 4 hours
];
