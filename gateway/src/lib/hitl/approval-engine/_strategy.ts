// ─── Zenic-Agents v3 — HITL Approval Strategy & Helpers ────────────────
// Split from approval-engine.ts — auto-approve evaluation, policy satisfaction, ID generation

import type { AutoApproveRule, ApprovalPolicy, CreateApprovalRequestInput } from "../types";
import { ApprovalPriority, ApprovalType } from "../types";

/** Evaluates whether an approval request can be auto-approved based on policy */
export function evaluateAutoApproveRules(
  input: CreateApprovalRequestInput,
  rules: AutoApproveRule[],
): { canAutoApprove: boolean; matchedRule: string | null } {
  for (const rule of rules) {
    if (!rule.enabled) continue;

    const cond = rule.condition;

    if (cond.allowedPriorities && cond.allowedPriorities.length > 0) {
      const priority = input.priority ?? ApprovalPriority.MEDIUM;
      if (!cond.allowedPriorities.includes(priority)) continue;
    }

    if (cond.allowedActionTypes && cond.allowedActionTypes.length > 0) {
      if (!cond.allowedActionTypes.includes(input.type)) continue;
    }

    if (cond.requiredTags && cond.requiredTags.length > 0) {
      const tags = input.tags ?? [];
      const hasAll = cond.requiredTags.every((t) => tags.includes(t));
      if (!hasAll) continue;
    }

    if (cond.maxAffectedResources !== undefined) {
      const resources = input.actionPayload?.resources;
      if (Array.isArray(resources) && resources.length > cond.maxAffectedResources) continue;
    }

    if (cond.maxAmount !== undefined) {
      const amount = input.actionPayload?.amount;
      if (typeof amount === "number" && amount > cond.maxAmount) continue;
    }

    if (rule.maxRiskScore !== undefined) {
      const riskScore = input.actionPayload?.riskScore;
      if (typeof riskScore === "number" && riskScore > rule.maxRiskScore) continue;
    }

    return { canAutoApprove: true, matchedRule: rule.name };
  }

  return { canAutoApprove: false, matchedRule: null };
}

/** Determines if the current approvals satisfy the approval policy */
export function isApprovalPolicySatisfied(
  policy: ApprovalPolicy,
  currentApprovals: number,
  requiredApprovals: number,
  _approvedRoles: string[],
): boolean {
  switch (policy.mode) {
    case "single":
      return currentApprovals >= 1;
    case "unanimous":
      return currentApprovals >= requiredApprovals;
    case "majority":
      return currentApprovals > Math.floor(requiredApprovals / 2);
    case "quorum":
      return currentApprovals >= (policy.quorum ?? requiredApprovals);
    case "auto_approve":
      return currentApprovals >= 1;
    default:
      return currentApprovals >= requiredApprovals;
  }
}

/** Generate a unique request ID */
export function generateRequestId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `hitl_${timestamp}_${random}`;
}
