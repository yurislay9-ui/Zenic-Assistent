// ─── Zenic-Agents v3 — HITL Approval Engine: Routing & Mutations ─────
// Strategy evaluation, ID generation, and write operation implementations
// extracted from the ApprovalEngine class for modularity.

import { db } from "@/lib/db";
import {
  type CreateApprovalRequestInput,
  type ApprovalRequest,
  type ApproveRequestInput,
  type RejectRequestInput,
  type ApprovalPolicy,
  type AutoApproveRule,
  ApprovalRequestStatus,
  ApprovalPriority,
  DecisionType,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";
import { mapDbRecordToModel, type DbApprovalRecord } from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// Strategy Pattern: Approval Policy Evaluator
// ═══════════════════════════════════════════════════════════════════════════

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
      if (!cond.requiredTags.every((t) => tags.includes(t))) continue;
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
  approvedRoles: string[],
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

// ═══════════════════════════════════════════════════════════════════════════
// ID Generation
// ═══════════════════════════════════════════════════════════════════════════

export function generateRequestId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `hitl_${timestamp}_${random}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Write Operations (mutation implementations)
// ═══════════════════════════════════════════════════════════════════════════

/** Create a new approval request */
export async function executeCreateRequest(input: CreateApprovalRequestInput): Promise<ApprovalRequest> {
  const requestId = generateRequestId();
  const priority = input.priority ?? ApprovalPriority.MEDIUM;
  const policy: ApprovalPolicy = input.approvalPolicy ?? {
    mode: "single",
    defaultReversible: input.isReversible ?? true,
    undoWindowMs: input.undoWindowMs,
  };

  const autoApproveRules = policy.autoApproveRules ?? [];
  const { canAutoApprove, matchedRule } = evaluateAutoApproveRules(input, autoApproveRules);

  const isReversible = policy.defaultReversible ?? input.isReversible ?? true;
  const undoWindowMs = policy.undoWindowMs ?? input.undoWindowMs;
  const deadline = input.deadline ? new Date(input.deadline) : null;
  const undoDeadline = undoWindowMs ? new Date(Date.now() + undoWindowMs) : null;
  const initialStatus = canAutoApprove ? ApprovalRequestStatus.APPROVED : ApprovalRequestStatus.PENDING;
  const currentApprovals = canAutoApprove ? 1 : 0;
  const requiredApprovals = input.requiredApprovals ?? 1;

  const record = await db.hitlApprovalRequest.create({
    data: {
      requestId, title: input.title, description: input.description,
      type: input.type, status: initialStatus, priority,
      requesterId: input.requesterId, requesterName: input.requesterName,
      targetResource: input.targetResource, targetAction: input.targetAction,
      actionPayload: JSON.stringify(input.actionPayload ?? {}),
      undoPayload: JSON.stringify(input.undoPayload ?? {}),
      isReversible, undoDeadline, requiredApprovals, currentApprovals,
      approvalPolicy: JSON.stringify(policy), deadline,
      parentId: input.parentId ?? null,
      tags: JSON.stringify(input.tags ?? []),
      metadata: JSON.stringify(input.metadata ?? {}),
    },
  });

  if (canAutoApprove) {
    await db.hitlApprovalDecision.create({
      data: {
        requestId: record.requestId, decision: DecisionType.APPROVED,
        decisionBy: "system", decisionByName: "System Auto-Approve",
        role: "system", comment: `Auto-approved by rule: ${matchedRule ?? "unknown"}`,
        delegatedFrom: null,
      },
    });
  }

  await recordAuditEvent({
    requestId: record.requestId,
    eventType: canAutoApprove ? HitlEventType.APPROVED : HitlEventType.CREATED,
    actorId: input.requesterId, actorName: input.requesterName,
    details: {
      title: input.title, type: input.type, priority,
      targetResource: input.targetResource, targetAction: input.targetAction,
      isReversible, autoApproved: canAutoApprove, autoApproveRule: matchedRule,
    },
  });

  await notifyApprovalEvent(
    canAutoApprove ? "approval_approved" : "approval_pending",
    {
      requestId: record.requestId, title: input.title, priority,
      requesterId: input.requesterId, requesterName: input.requesterName,
      autoApproved: canAutoApprove,
    },
  );

  return mapDbRecordToModel(record as unknown as DbApprovalRecord);
}

/** Approve a request — uses $transaction + atomic increment */
export async function executeApproveRequest(requestId: string, input: ApproveRequestInput): Promise<ApprovalRequest> {
  const { updated, isFullyApproved, actualApprovalCount, requiredApprovals, recordTitle, recordPriority } =
    await db.$transaction(async (tx) => {
      const record = await tx.hitlApprovalRequest.findUnique({ where: { requestId } });
      if (!record) throw new Error(`Approval request "${requestId}" not found`);
      if (record.status !== ApprovalRequestStatus.PENDING && record.status !== ApprovalRequestStatus.ESCALATED) {
        throw new Error(`Cannot approve request in status "${record.status}"`);
      }

      const existingDecision = await tx.hitlApprovalDecision.findFirst({
        where: { requestId, decisionBy: input.decisionBy, decision: DecisionType.APPROVED },
      });
      if (existingDecision) throw new Error(`User "${input.decisionByName}" has already approved this request`);

      await tx.hitlApprovalDecision.create({
        data: {
          requestId, decision: DecisionType.APPROVED,
          decisionBy: input.decisionBy, decisionByName: input.decisionByName,
          role: input.role, comment: input.comment ?? "",
          delegatedFrom: input.delegatedFrom ?? null,
        },
      });

      const policy: ApprovalPolicy = JSON.parse(record.approvalPolicy);
      const afterUpdate = await tx.hitlApprovalRequest.update({
        where: { requestId },
        data: { currentApprovals: { increment: 1 } },
      });

      const actualApprovalCount = afterUpdate.currentApprovals;
      const isFullyApproved = isApprovalPolicySatisfied(policy, actualApprovalCount, record.requiredApprovals, []);

      const updated = isFullyApproved
        ? await tx.hitlApprovalRequest.update({
            where: { requestId },
            data: { status: ApprovalRequestStatus.APPROVED, executedAt: new Date() },
          })
        : afterUpdate;

      return {
        updated, isFullyApproved, actualApprovalCount,
        requiredApprovals: record.requiredApprovals,
        recordTitle: record.title, recordPriority: record.priority as ApprovalPriority,
      };
    });

  await recordAuditEvent({
    requestId, eventType: HitlEventType.APPROVED,
    actorId: input.decisionBy, actorName: input.decisionByName,
    details: {
      comment: input.comment, delegatedFrom: input.delegatedFrom,
      fullyApproved: isFullyApproved, currentApprovals: actualApprovalCount, requiredApprovals,
    },
  });

  await notifyApprovalEvent(
    isFullyApproved ? "approval_approved" : "approval_pending",
    {
      requestId, title: recordTitle, priority: recordPriority,
      approverName: input.decisionByName,
      fullyApproved: isFullyApproved, currentApprovals: actualApprovalCount, requiredApprovals,
    },
  );

  return mapDbRecordToModel(updated as unknown as DbApprovalRecord);
}

/** Reject a request — atomic within $transaction */
export async function executeRejectRequest(requestId: string, input: RejectRequestInput): Promise<ApprovalRequest> {
  const { updated, recordTitle, recordPriority, recordRequesterId } = await db.$transaction(async (tx) => {
    const record = await tx.hitlApprovalRequest.findUnique({ where: { requestId } });
    if (!record) throw new Error(`Approval request "${requestId}" not found`);
    if (record.status !== ApprovalRequestStatus.PENDING && record.status !== ApprovalRequestStatus.ESCALATED) {
      throw new Error(`Cannot reject request in status "${record.status}"`);
    }

    await tx.hitlApprovalDecision.create({
      data: {
        requestId, decision: DecisionType.REJECTED,
        decisionBy: input.decisionBy, decisionByName: input.decisionByName,
        role: input.role, comment: input.comment, delegatedFrom: null,
      },
    });

    const updated = await tx.hitlApprovalRequest.update({
      where: { requestId },
      data: { status: ApprovalRequestStatus.REJECTED },
    });

    return {
      updated,
      recordTitle: record.title, recordPriority: record.priority as ApprovalPriority,
      recordRequesterId: record.requesterId,
    };
  });

  await recordAuditEvent({
    requestId, eventType: HitlEventType.REJECTED,
    actorId: input.decisionBy, actorName: input.decisionByName,
    details: { comment: input.comment, role: input.role },
  });

  await notifyApprovalEvent("approval_rejected", {
    requestId, title: recordTitle, priority: recordPriority,
    rejecterName: input.decisionByName, reason: input.comment, requesterId: recordRequesterId,
  });

  return mapDbRecordToModel(updated as unknown as DbApprovalRecord);
}
