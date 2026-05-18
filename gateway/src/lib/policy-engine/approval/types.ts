// ─── Zenic-Agents v3 — Policy Approval Workflow Engine ──────────────────
// Phase 4: Declarative Versioned Policy Engine — Approval Workflow
//
// Design Patterns:
//   - State Machine: Approval lifecycle (draft → pending_review → approved → deployed / rejected / cancelled / expired / rolled_back)
//   - Chain of Responsibility: Auto-approve rules evaluated sequentially
//   - Command: ApprovalDecision as a command object for approval/rejection actions

import { db } from "@/lib/db";
import { createVersion, rollbackToVersion } from "./versioning";
import { computeContentHash } from "./yaml-loader";
import type { PolicyDocument } from "./types";
import type {
  PolicyApprovalRequest,
  ApprovalStatus,
  ApprovalPriority,
  ApprovalDecision,
  AutoApproveRule,
  AutoApproveCondition,
} from "./types";
import {
  ApprovalStatus as ApprovalStatusEnum,
  ApprovalPriority as ApprovalPriorityEnum,
} from "./types";

// ─── State Machine: Valid Transitions ─────────────────────────────────

/** Valid state transitions for the approval lifecycle */
const VALID_TRANSITIONS: Record<string, readonly string[]> = {
  draft: ["pending_review", "cancelled"] as const,
  pending_review: ["approved", "rejected", "cancelled", "expired"] as const,
  approved: ["deployed", "cancelled"] as const,
  rejected: [] as const,
  cancelled: [] as const,
  expired: [] as const,
  deployed: ["rolled_back"] as const,
  rolled_back: [] as const,
};

/**
 * Validate that a state transition is allowed.
 * @throws Error if the transition is invalid
 */
function validateTransition(currentStatus: string, targetStatus: string): void {
  const allowed = VALID_TRANSITIONS[currentStatus];
  if (!allowed || !allowed.includes(targetStatus)) {
    throw new Error(
      `Invalid state transition: "${currentStatus}" → "${targetStatus}". ` +
      `Allowed transitions from "${currentStatus}": [${(allowed ?? []).join(", ")}]`
    );
  }
}

// ─── Create Approval Request Input ────────────────────────────────────

/** Input for creating a new approval request */
export interface CreateApprovalRequestInput {
  /** Request title */
  title: string;
  /** Description of the proposed change */
  description: string;
  /** The proposed policy document */
  proposedDocument: PolicyDocument;
  /** Priority level */
  priority?: ApprovalPriority;
  /** Target policy ID (for modifications) */
  targetPolicyId?: string;
  /** Previous version (for rollback capability) */
  previousVersion?: string;
  /** Simulation result ID (if what-if was run) */
  simulationId?: string;
  /** Who requested this change */
  requestedBy: string;
  /** Required reviewer roles (overrides auto-calculated) */
  requiredReviewerRoles?: string[];
  /** Auto-approve rules (overrides defaults) */
  autoApproveRules?: AutoApproveRule[];
  /** Expiry in hours from now (default 72) */
  expiryHours?: number;
}

/** Listing filter options */
export interface ApprovalListOptions {
  /** Filter by status */
  status?: ApprovalStatus | ApprovalStatus[];
  /** Filter by priority */
  priority?: ApprovalPriority | ApprovalPriority[];
  /** Filter by requester */
  requestedBy?: string;
  /** Filter by target policy */
  targetPolicyId?: string;
  /** Maximum results (default 50) */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

// ─── Chain of Responsibility: Auto-Approve Rule Checkers ──────────────

/**
 * Auto-approve rule checker interface.
 * Each checker evaluates a single condition on the auto-approve rule.
 * If any checker fails, the rule does not pass.
 * Chain of Responsibility: checkers are invoked sequentially; all must pass.
 */
interface AutoApproveRuleChecker {
  /** The condition field this checker handles */
  field: keyof AutoApproveCondition;
  /** Evaluate the condition against the proposed and existing documents */
  check(
    condition: NonNullable<AutoApproveCondition[keyof AutoApproveCondition]>,
    proposedDocument: PolicyDocument,
    existingDocument: PolicyDocument | null,
  ): boolean;
}

/** Label match checker: proposed policy labels must match */
const labelMatchChecker: AutoApproveRuleChecker = {
  field: "labelMatch",
  check(condition, proposedDocument, _existingDocument): boolean {
    const requiredLabels = condition as Record<string, string>;
    const policyLabels = proposedDocument.metadata.labels ?? {};
    for (const [key, value] of Object.entries(requiredLabels)) {
      if (policyLabels[key] !== value) {
        return false;
      }
    }
    return true;
  },
};

/** Max statements changed checker: number of changed statements must be below threshold */
const maxStatementsChangedChecker: AutoApproveRuleChecker = {
  field: "maxStatementsChanged",
  check(condition, proposedDocument, existingDocument): boolean {
    const maxChanged = condition as number;
    if (!existingDocument) {
      // New policy — all statements are "new"
      return proposedDocument.statements.length <= maxChanged;
    }
    const existingIds = new Set(existingDocument.statements.map((s) => s.id));
    const proposedIds = new Set(proposedDocument.statements.map((s) => s.id));
    const added = proposedDocument.statements.filter((s) => !existingIds.has(s.id)).length;
    const removed = existingDocument.statements.filter((s) => !proposedIds.has(s.id)).length;
    return (added + removed) <= maxChanged;
  },
};

/** Allowed effect changes checker: effect changes must be in the allowed set */
const allowedEffectChangesChecker: AutoApproveRuleChecker = {
