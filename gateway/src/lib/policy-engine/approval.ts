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
  field: "allowedEffectChanges",
  check(condition, proposedDocument, existingDocument): boolean {
    const allowedEffects = condition as string[];
    if (!existingDocument) return true; // No existing doc = no effect changes
    const existingMap = new Map(existingDocument.statements.map((s) => [s.id, s.effect]));
    for (const stmt of proposedDocument.statements) {
      const existingEffect = existingMap.get(stmt.id);
      if (existingEffect !== undefined && existingEffect !== stmt.effect) {
        if (!allowedEffects.includes(stmt.effect)) {
          return false;
        }
      }
    }
    return true;
  },
};

/** Exclude compliance standards checker: no changes to listed compliance standards */
const excludeComplianceStandardsChecker: AutoApproveRuleChecker = {
  field: "excludeComplianceStandards",
  check(condition, proposedDocument, existingDocument): boolean {
    const excludedStandards = condition as string[];
    if (excludedStandards.length === 0) return true;

    const proposedCompliance = proposedDocument.metadata.compliance ?? [];
    const proposedStandards = new Set(proposedCompliance.map((c) => c.standard));

    if (!existingDocument) {
      // New policy — check if it touches excluded standards
      for (const std of excludedStandards) {
        if (proposedStandards.has(std)) return false;
      }
      return true;
    }

    const existingCompliance = existingDocument.metadata.compliance ?? [];
    const existingStandards = new Set(existingCompliance.map((c) => c.standard));

    // Check if any excluded standard is affected (added or removed)
    for (const std of excludedStandards) {
      const wasPresent = existingStandards.has(std);
      const isPresent = proposedStandards.has(std);
      if (wasPresent !== isPresent) return false;
    }
    return true;
  },
};

/** Max new denials checker: new denials must be below threshold */
const maxNewDenialsChecker: AutoApproveRuleChecker = {
  field: "maxNewDenials",
  check(condition, proposedDocument, existingDocument): boolean {
    const maxNewDenials = condition as number;
    if (!existingDocument) {
      // New policy — count all deny statements
      const denials = proposedDocument.statements.filter(
        (s) => s.effect === "deny"
      ).length;
      return denials <= maxNewDenials;
    }
    const existingDenyIds = new Set(
      existingDocument.statements
        .filter((s) => s.effect === "deny")
        .map((s) => s.id)
    );
    const newDenials = proposedDocument.statements.filter(
      (s) => s.effect === "deny" && !existingDenyIds.has(s.id)
    ).length;
    return newDenials <= maxNewDenials;
  },
};

/** All auto-approve rule checkers, ordered */
const AUTO_APPROVE_CHECKERS: AutoApproveRuleChecker[] = [
  labelMatchChecker,
  maxStatementsChangedChecker,
  allowedEffectChangesChecker,
  excludeComplianceStandardsChecker,
  maxNewDenialsChecker,
];

/**
 * Evaluate all auto-approve rules against the proposed change.
 * Chain of Responsibility: each rule is evaluated; all enabled rules must pass.
 * Returns true if all active rules pass → auto-approve.
 */
function evaluateAutoApproveRules(
  rules: AutoApproveRule[],
  proposedDocument: PolicyDocument,
  existingDocument: PolicyDocument | null,
): boolean {
  const enabledRules = rules.filter((r) => r.enabled);
  if (enabledRules.length === 0) return false;

  for (const rule of enabledRules) {
    const rulePasses = evaluateSingleRule(rule, proposedDocument, existingDocument);
    if (!rulePasses) return false;
  }
  return true;
}

/**
 * Evaluate a single auto-approve rule.
 * All specified conditions in the rule must pass.
 */
function evaluateSingleRule(
  rule: AutoApproveRule,
  proposedDocument: PolicyDocument,
  existingDocument: PolicyDocument | null,
): boolean {
  const condition = rule.condition;
  for (const checker of AUTO_APPROVE_CHECKERS) {
    const fieldValue = condition[checker.field];
    if (fieldValue !== undefined && fieldValue !== null) {
      if (!checker.check(fieldValue, proposedDocument, existingDocument)) {
        return false;
      }
    }
  }
  return true;
}

// ─── Required Approvals Calculation ──────────────────────────────────

/** Priority-based default approval counts */
const PRIORITY_APPROVAL_MAP: Record<string, number> = {
  low: 1,
  medium: 1,
  high: 2,
  critical: 2,
  emergency: 1,
};

/** Default reviewer roles by priority */
const PRIORITY_REVIEWER_ROLES: Record<string, string[]> = {
  low: ["policy_reviewer"],
  medium: ["policy_reviewer"],
  high: ["policy_reviewer", "policy_admin"],
  critical: ["policy_admin", "compliance_officer"],
  emergency: ["policy_admin"],
};

/**
 * Calculate the required number of approvals based on policy risk.
 * Factors: priority, number of deny statements, compliance standards involved.
 */
function calculateRequiredApprovals(
  proposedDocument: PolicyDocument,
  priority: ApprovalPriority,
): number {
  let required = PRIORITY_APPROVAL_MAP[priority] ?? 1;

  // Additional approval for policies with many deny statements
  const denyCount = proposedDocument.statements.filter(
    (s) => s.effect === "deny"
  ).length;
  if (denyCount >= 3) {
    required += 1;
  }

  // Additional approval for policies touching compliance standards
  const compliance = proposedDocument.metadata.compliance ?? [];
  if (compliance.length >= 2) {
    required += 1;
  }

  return required;
}

/**
 * Calculate required reviewer roles based on priority and document content.
 */
function calculateRequiredReviewerRoles(
  proposedDocument: PolicyDocument,
  priority: ApprovalPriority,
): string[] {
  const roles = [...(PRIORITY_REVIEWER_ROLES[priority] ?? ["policy_reviewer"])];

  // Add compliance officer if compliance standards are involved
  const compliance = proposedDocument.metadata.compliance ?? [];
  if (compliance.length > 0 && !roles.includes("compliance_officer")) {
    roles.push("compliance_officer");
  }

  return roles;
}

// ─── DB ↔ Domain Mapping ─────────────────────────────────────────────

/**
 * Map a Prisma PolicyApproval record to the domain PolicyApprovalRequest.
 */
function mapDbToApprovalRequest(record: {
  id: string;
  approvalId: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  targetPolicyId: string | null;
  previousVersion: string | null;
  proposedDocument: string;
  simulationId: string | null;
  requestedBy: string;
  requiredApprovals: number;
  currentApprovals: number;
  approvals: string;
  requiredReviewerRoles: string;
  autoApproveRules: string;
  autoApproved: boolean;
  expiresAt: Date | null;
  deployedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}): PolicyApprovalRequest {
  return {
    id: record.approvalId,
    title: record.title,
    description: record.description,
    status: record.status as ApprovalStatus,
    priority: record.priority as ApprovalPriority,
    proposedDocument: JSON.parse(record.proposedDocument) as PolicyDocument,
    targetPolicyId: record.targetPolicyId ?? undefined,
    previousVersion: record.previousVersion ?? undefined,
    simulationId: record.simulationId ?? undefined,
    requestedBy: record.requestedBy,
    requiredApprovals: record.requiredApprovals,
    approvals: JSON.parse(record.approvals) as ApprovalDecision[],
    requiredReviewerRoles: JSON.parse(record.requiredReviewerRoles) as string[],
    autoApproveRules: JSON.parse(record.autoApproveRules) as AutoApproveRule[],
    autoApproved: record.autoApproved,
    expiresAt: record.expiresAt?.toISOString() ?? undefined,
    createdAt: record.createdAt.toISOString(),
    updatedAt: record.updatedAt.toISOString(),
    deployedAt: record.deployedAt?.toISOString() ?? undefined,
  };
}

/**
 * Load the existing PolicyDocument for a target policy (if any).
 */
async function loadExistingDocument(
  targetPolicyId?: string | null,
): Promise<PolicyDocument | null> {
  if (!targetPolicyId) return null;

  const policy = await db.declPolicy.findUnique({
    where: { policyId: targetPolicyId },
  });
  if (!policy) return null;

  try {
    // The statements field is JSON; try to reconstruct the full document
    // First check if versions exist with full document snapshots
    const activeVersion = await db.declPolicyVersion.findFirst({
      where: { declPolicyId: policy.id, status: "active" },
      orderBy: { createdAt: "desc" },
    });

    if (activeVersion) {
      return JSON.parse(activeVersion.document) as PolicyDocument;
    }

    // Fallback: reconstruct from policy fields
    return {
      apiVersion: policy.apiVersion as "policy.zenic.dev/v1",
      kind: "PolicyDocument" as const,
      metadata: {
        id: policy.policyId,
        name: policy.name,
        version: policy.version,
        description: policy.description,
        labels: JSON.parse(policy.labels) as Record<string, string>,
        compliance: JSON.parse(policy.compliance) as PolicyDocument["metadata"]["compliance"],
        author: policy.author ?? undefined,
        createdAt: policy.createdAt.toISOString(),
        updatedAt: policy.updatedAt.toISOString(),
      },
      statements: JSON.parse(policy.statements) as PolicyDocument["statements"],
      tests: JSON.parse(policy.tests) as PolicyDocument["tests"],
    };
  } catch {
    return null;
  }
}

/**
 * Generate a unique approval ID.
 */
function generateApprovalId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).substring(2, 10);
  return `apr_${ts}_${rand}`;
}

// ─── Public API Functions ─────────────────────────────────────────────

/**
 * Create a new approval request.
 *
 * 1. Validate proposed document
 * 2. Set initial status to "draft"
 * 3. Calculate required approvals based on policy risk
 * 4. Set expiry date (default 72 hours)
 * 5. Check auto-approve rules
 * 6. Persist to PolicyApproval table
 */
export async function createApprovalRequest(
  input: CreateApprovalRequestInput,
): Promise<PolicyApprovalRequest> {
  const {
    title,
    description,
    proposedDocument,
    priority = ApprovalPriorityEnum.MEDIUM,
    targetPolicyId,
    previousVersion,
    simulationId,
    requestedBy,
    requiredReviewerRoles,
    autoApproveRules,
    expiryHours = 72,
  } = input;

  // 1. Validate proposed document
  validateProposedDocument(proposedDocument);

  // 2. Calculate required approvals based on policy risk
  const requiredApprovals = calculateRequiredApprovals(proposedDocument, priority);

  // 3. Calculate required reviewer roles
  const reviewerRoles = requiredReviewerRoles ?? calculateRequiredReviewerRoles(proposedDocument, priority);

  // 4. Resolve auto-approve rules (use provided or default empty)
  const rules = autoApproveRules ?? [];

  // 5. Set expiry date
  const expiresAt = new Date(Date.now() + expiryHours * 60 * 60 * 1000);

  // 6. Generate unique approval ID
  const approvalId = generateApprovalId();

  // 7. Persist to database with initial status "draft"
  const record = await db.policyApproval.create({
    data: {
      approvalId,
      title,
      description,
      status: ApprovalStatusEnum.DRAFT,
      priority,
      targetPolicyId: targetPolicyId ?? null,
      previousVersion: previousVersion ?? null,
      proposedDocument: JSON.stringify(proposedDocument),
      simulationId: simulationId ?? null,
      requestedBy,
      requiredApprovals,
      currentApprovals: 0,
      approvals: "[]",
      requiredReviewerRoles: JSON.stringify(reviewerRoles),
      autoApproveRules: JSON.stringify(rules),
      autoApproved: false,
      expiresAt,
      deployedAt: null,
    },
  });

  return mapDbToApprovalRequest(record);
}

/**
 * Submit an approval request for review.
 * Moves from "draft" to "pending_review".
 * If auto-approve rules match → auto-approve immediately.
 */
export async function submitForReview(
  approvalId: string,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Validate state transition
  validateTransition(record.status, ApprovalStatusEnum.PENDING_REVIEW);

  // Validate required fields for submission
  if (!record.title || !record.proposedDocument || !record.requestedBy) {
    throw new Error("Cannot submit for review: missing required fields (title, proposedDocument, requestedBy)");
  }

  // Check auto-approve rules
  const proposedDocument = JSON.parse(record.proposedDocument) as PolicyDocument;
  const existingDocument = await loadExistingDocument(record.targetPolicyId);
  const autoApproveRules = JSON.parse(record.autoApproveRules) as AutoApproveRule[];

  const shouldAutoApprove = evaluateAutoApproveRules(autoApproveRules, proposedDocument, existingDocument);

  const newStatus = shouldAutoApprove
    ? ApprovalStatusEnum.APPROVED
    : ApprovalStatusEnum.PENDING_REVIEW;

  // Update the record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: newStatus,
      autoApproved: shouldAutoApprove,
      currentApprovals: shouldAutoApprove
        ? record.requiredApprovals
        : record.currentApprovals,
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Add an approval or rejection decision to an approval request.
 * Command pattern: ApprovalDecision is the command object.
 *
 * - If rejection → set status to "rejected"
 * - If approval → increment currentApprovals
 * - If currentApprovals >= requiredApprovals → set status to "approved"
 * - Validate reviewer has required role
 */
export async function approveRequest(
  approvalId: string,
  decision: ApprovalDecision,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Only pending_review requests can receive decisions
  if (record.status !== ApprovalStatusEnum.PENDING_REVIEW) {
    throw new Error(
      `Cannot add decision to approval request in "${record.status}" status. ` +
      `Expected "${ApprovalStatusEnum.PENDING_REVIEW}".`
    );
  }

  // Validate reviewer has a required role
  const requiredRoles = JSON.parse(record.requiredReviewerRoles) as string[];
  if (requiredRoles.length > 0 && !requiredRoles.includes(decision.role)) {
    throw new Error(
      `Reviewer role "${decision.role}" is not authorized. ` +
      `Required roles: [${requiredRoles.join(", ")}]`
    );
  }

  // Check for duplicate reviewer
  const existingApprovals = JSON.parse(record.approvals) as ApprovalDecision[];
  const alreadyReviewed = existingApprovals.some((a) => a.reviewerId === decision.reviewerId);
  if (alreadyReviewed) {
    throw new Error(
      `Reviewer "${decision.reviewerId}" has already submitted a decision on this request.`
    );
  }

  // Apply the decision (Command pattern)
  const updatedApprovals = [...existingApprovals, decision];
  let newStatus: string = record.status;
  let newCurrentApprovals = record.currentApprovals;

  if (decision.decision === "rejected") {
    // Rejection → set status to "rejected"
    validateTransition(record.status, ApprovalStatusEnum.REJECTED);
    newStatus = ApprovalStatusEnum.REJECTED;
  } else {
    // Approval → increment currentApprovals
    // BUG #12 FIX: Atomic increment inside transaction to prevent race condition
    // where two concurrent reviewers both read the same count and both increment by 1
    // but one increment is lost.
    newCurrentApprovals = record.currentApprovals + 1;
    if (newCurrentApprovals >= record.requiredApprovals) {
      // Enough approvals → set status to "approved"
      validateTransition(record.status, ApprovalStatusEnum.APPROVED);
      newStatus = ApprovalStatusEnum.APPROVED;
    }
  }

  // BUG #12 FIX: Use $transaction to ensure atomic read-modify-write
  const updated = await db.$transaction(async (tx) => {
    // Re-read inside transaction to get the latest state
    const freshRecord = await tx.policyApproval.findUnique({
      where: { approvalId },
    });
    if (!freshRecord) {
      throw new Error(`Approval request "${approvalId}" not found during transaction`);
    }

    // Re-validate: still in pending_review?
    if (freshRecord.status !== ApprovalStatusEnum.PENDING_REVIEW) {
      throw new Error(
        `Approval request "${approvalId}" status changed to "${freshRecord.status}" during review. Please retry.`
      );
    }

    // Merge approvals from concurrent reviewers
    const freshApprovals = JSON.parse(freshRecord.approvals) as ApprovalDecision[];
    const mergedApprovals = [...freshApprovals, decision];

    let finalStatus = freshRecord.status;
    let finalCurrentApprovals = freshRecord.currentApprovals;

    if (decision.decision === "rejected") {
      finalStatus = ApprovalStatusEnum.REJECTED;
    } else {
      finalCurrentApprovals = freshRecord.currentApprovals + 1;
      if (finalCurrentApprovals >= freshRecord.requiredApprovals) {
        finalStatus = ApprovalStatusEnum.APPROVED;
      }
    }

    return tx.policyApproval.update({
      where: { approvalId },
      data: {
        status: finalStatus,
        currentApprovals: finalCurrentApprovals,
        approvals: JSON.stringify(mergedApprovals),
        updatedAt: new Date(),
      },
    });
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Deploy an approved policy change.
 *
 * - Only if status is "approved"
 * - Use versioning.ts createVersion to create a new version
 * - Update DeclPolicy with new content
 * - Set status to "deployed"
 * - Record deployment timestamp
 */
export async function deployApproval(
  approvalId: string,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Validate state transition
  validateTransition(record.status, ApprovalStatusEnum.DEPLOYED);

  const proposedDocument = JSON.parse(record.proposedDocument) as PolicyDocument;
  const policyId = record.targetPolicyId ?? proposedDocument.metadata.id;

  // Use versioning.ts createVersion to create a new version
  await createVersion({
    policyId,
    document: proposedDocument,
    changeDescription: record.description,
    createdBy: record.requestedBy,
  });

  // Update DeclPolicy with new content (createVersion already does this,
  // but we also update the contentHash explicitly)
  const newContentHash = computeContentHash(proposedDocument);
  await db.declPolicy.update({
    where: { policyId },
    data: {
      contentHash: newContentHash,
      version: proposedDocument.metadata.version,
      statements: JSON.stringify(proposedDocument.statements),
      tests: JSON.stringify(proposedDocument.tests ?? []),
      labels: JSON.stringify(proposedDocument.metadata.labels ?? {}),
      compliance: JSON.stringify(proposedDocument.metadata.compliance ?? []),
      updatedAt: new Date(),
    },
  });

  // Update the approval record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: ApprovalStatusEnum.DEPLOYED,
      deployedAt: new Date(),
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Cancel an approval request.
 * Can cancel from draft, pending_review, or approved states.
 */
export async function cancelApproval(
  approvalId: string,
  cancelledBy: string,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Validate state transition
  validateTransition(record.status, ApprovalStatusEnum.CANCELLED);

  // Add a cancellation note to approvals
  const existingApprovals = JSON.parse(record.approvals) as ApprovalDecision[];
  const cancellationDecision: ApprovalDecision = {
    reviewerId: cancelledBy,
    reviewerName: cancelledBy,
    decision: "rejected",
    role: "requester",
    comment: "Request cancelled by requester",
    decidedAt: new Date().toISOString(),
  };

  // Update the record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: ApprovalStatusEnum.CANCELLED,
      approvals: JSON.stringify([...existingApprovals, cancellationDecision]),
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Rollback a deployed approval to the previous version.
 *
 * - Only if status is "deployed"
 * - Use versioning.ts rollbackToVersion
 * - Set status to "rolled_back"
 */
export async function rollbackApproval(
  approvalId: string,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Validate state transition
  validateTransition(record.status, ApprovalStatusEnum.ROLLED_BACK);

  // Determine the previous version to rollback to
  const previousVersion = record.previousVersion;
  const policyId = record.targetPolicyId;

  if (!policyId) {
    throw new Error(
      `Cannot rollback approval "${approvalId}": no targetPolicyId associated with this request.`
    );
  }

  if (previousVersion) {
    // Rollback to specific previous version using versioning.ts
    await rollbackToVersion(
      policyId,
      previousVersion,
      record.requestedBy,
      `Rollback via approval workflow: ${record.title}`,
    );
  } else {
    // No explicit previous version — find the previous version in the version chain
    const policy = await db.declPolicy.findUnique({
      where: { policyId },
    });
    if (!policy) {
      throw new Error(`Policy "${policyId}" not found for rollback`);
    }

    // Find the most recent superseded version (the one before current)
    const supersededVersion = await db.declPolicyVersion.findFirst({
      where: { declPolicyId: policy.id, status: "superseded" },
      orderBy: { createdAt: "desc" },
    });

    if (supersededVersion) {
      const supersededDoc = JSON.parse(supersededVersion.document) as PolicyDocument;
      await rollbackToVersion(
        policyId,
        supersededVersion.version,
        record.requestedBy,
        `Rollback via approval workflow (auto-detected previous version): ${record.title}`,
      );
    } else {
      throw new Error(
        `Cannot rollback approval "${approvalId}": no previous version found for policy "${policyId}".`
      );
    }
  }

  // Update the approval record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: ApprovalStatusEnum.ROLLED_BACK,
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Find and expire approval requests past their expiry date.
 * Sets status to "expired" for all expired requests that are still in reviewable states.
 * Returns the number of expired requests.
 */
export async function checkExpiredApprovals(): Promise<number> {
  const now = new Date();

  // Find all requests that are past expiry and in an expirable state
  const expiredRequests = await db.policyApproval.findMany({
    where: {
      status: { in: [ApprovalStatusEnum.DRAFT, ApprovalStatusEnum.PENDING_REVIEW] },
      expiresAt: { not: null, lt: now },
    },
  });

  if (expiredRequests.length === 0) return 0;

  // Update all expired requests
  const updatePromises = expiredRequests.map((req) =>
    db.policyApproval.update({
      where: { approvalId: req.approvalId },
      data: {
        status: ApprovalStatusEnum.EXPIRED,
        updatedAt: now,
      },
    })
  );

  await Promise.all(updatePromises);

  return expiredRequests.length;
}

/**
 * Load a single approval request by ID.
 */
export async function getApprovalRequest(
  approvalId: string,
): Promise<PolicyApprovalRequest | null> {
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });

  if (!record) return null;

  return mapDbToApprovalRequest(record);
}

/**
 * List approval requests with filtering and pagination.
 */
export async function listApprovalRequests(
  options?: ApprovalListOptions,
): Promise<{ requests: PolicyApprovalRequest[]; total: number }> {
  const {
    status,
    priority,
    requestedBy,
    targetPolicyId,
    limit = 50,
    offset = 0,
  } = options ?? {};

  // Build where clause
  const where: Record<string, unknown> = {};

  if (status) {
    if (Array.isArray(status)) {
      where.status = { in: status };
    } else {
      where.status = status;
    }
  }

  if (priority) {
    if (Array.isArray(priority)) {
      where.priority = { in: priority };
    } else {
      where.priority = priority;
    }
  }

  if (requestedBy) {
    where.requestedBy = requestedBy;
  }

  if (targetPolicyId) {
    where.targetPolicyId = targetPolicyId;
  }

  const [records, total] = await Promise.all([
    db.policyApproval.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: limit,
      skip: offset,
    }),
    db.policyApproval.count({ where }),
  ]);

  const requests = records.map(mapDbToApprovalRequest);

  return { requests, total };
}

// ─── Validation Helpers ──────────────────────────────────────────────

/**
 * Validate a proposed policy document has all required fields.
 * @throws Error if the document is invalid
 */
function validateProposedDocument(document: PolicyDocument): void {
  if (!document.apiVersion) {
    throw new Error("Proposed document must have an apiVersion");
  }
  if (!document.kind) {
    throw new Error("Proposed document must have a kind");
  }
  if (!document.metadata?.id) {
    throw new Error("Proposed document must have metadata.id");
  }
  if (!document.metadata?.name) {
    throw new Error("Proposed document must have metadata.name");
  }
  if (!document.metadata?.version) {
    throw new Error("Proposed document must have metadata.version");
  }
  if (!document.metadata?.description) {
    throw new Error("Proposed document must have metadata.description");
  }
  if (!Array.isArray(document.statements)) {
    throw new Error("Proposed document must have a statements array");
  }
  // Validate each statement
  for (let i = 0; i < document.statements.length; i++) {
    const stmt = document.statements[i];
    if (!stmt.id) {
      throw new Error(`Statement at index ${i} must have an id`);
    }
    if (!stmt.effect) {
      throw new Error(`Statement "${stmt.id}" must have an effect`);
    }
    if (!stmt.resource) {
      throw new Error(`Statement "${stmt.id}" must have a resource`);
    }
    if (!stmt.action) {
      throw new Error(`Statement "${stmt.id}" must have an action`);
    }
  }
}
