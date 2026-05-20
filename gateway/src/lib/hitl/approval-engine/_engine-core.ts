// ─── Zenic-Agents v3 — Approval Engine Core ───────────────────────────
// Split from approval-engine.ts — ApprovalEngine class with core CRUD operations

import { db } from "@/lib/db";
import {
  type CreateApprovalRequestInput,
  type ApprovalRequest,
  type ApproveRequestInput,
  type RejectRequestInput,
  type ApprovalPolicy,
  type ApprovalStats,
  type ApprovalListOptions,
  ApprovalRequestStatus,
  ApprovalPriority,
  ApprovalType,
  DecisionType,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";
import { evaluateAutoApproveRules, isApprovalPolicySatisfied, generateRequestId } from "./_strategy";

/** Map a database record to the domain model */
export function mapRecordToModel(record: {
  id: string; requestId: string; title: string; description: string;
  type: string; status: string; priority: string; requesterId: string;
  requesterName: string; targetResource: string; targetAction: string;
  actionPayload: string; undoPayload: string; isReversible: boolean;
  undoDeadline: Date | null; undoExecutedAt: Date | null;
  executedAt: Date | null; executionResult: string | null;
  requiredApprovals: number; currentApprovals: number;
  approvalPolicy: string; deadline: Date | null; escalationLevel: number;
  parentId: string | null; tags: string; metadata: string;
  createdAt: Date; updatedAt: Date;
}): ApprovalRequest {
  return {
    id: record.id,
    requestId: record.requestId,
    title: record.title,
    description: record.description,
    type: record.type as ApprovalType,
    status: record.status as ApprovalRequestStatus,
    priority: record.priority as ApprovalPriority,
    requesterId: record.requesterId,
    requesterName: record.requesterName,
    targetResource: record.targetResource,
    targetAction: record.targetAction,
    actionPayload: JSON.parse(record.actionPayload),
    undoPayload: JSON.parse(record.undoPayload),
    isReversible: record.isReversible,
    undoDeadline: record.undoDeadline?.toISOString() ?? null,
    undoExecutedAt: record.undoExecutedAt?.toISOString() ?? null,
    executedAt: record.executedAt?.toISOString() ?? null,
    executionResult: record.executionResult ? JSON.parse(record.executionResult) : null,
    requiredApprovals: record.requiredApprovals,
    currentApprovals: record.currentApprovals,
    approvalPolicy: JSON.parse(record.approvalPolicy),
    deadline: record.deadline?.toISOString() ?? null,
    escalationLevel: record.escalationLevel,
    parentId: record.parentId,
    tags: JSON.parse(record.tags),
    metadata: JSON.parse(record.metadata),
    createdAt: record.createdAt.toISOString(),
    updatedAt: record.updatedAt.toISOString(),
  };
}

export class ApprovalEngine {
  static instance: ApprovalEngine | null = null;

  private constructor() {}

  static getInstance(): ApprovalEngine {
    if (!ApprovalEngine.instance) {
      ApprovalEngine.instance = new ApprovalEngine();
    }
    return ApprovalEngine.instance;
  }

  async createRequest(input: CreateApprovalRequestInput): Promise<ApprovalRequest> {
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
      details: { title: input.title, type: input.type, priority,
        targetResource: input.targetResource, targetAction: input.targetAction,
        isReversible, autoApproved: canAutoApprove, autoApproveRule: matchedRule },
    });

    await notifyApprovalEvent(
      canAutoApprove ? "approval_approved" : "approval_pending",
      { requestId: record.requestId, title: input.title, priority,
        requesterId: input.requesterId, requesterName: input.requesterName,
        autoApproved: canAutoApprove },
    );

    return mapRecordToModel(record);
  }

  async getRequest(requestId: string): Promise<ApprovalRequest | null> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
      include: { decisions: true, delegations: true, escalations: true, undoActions: true },
    });
    if (!record) return null;
    return mapRecordToModel(record);
  }

  async listRequests(options: ApprovalListOptions = {}): Promise<{
    data: ApprovalRequest[]; total: number; page: number; pageSize: number;
  }> {
    const { status, priority, requesterId, type, targetResource,
      page = 1, pageSize = 20, sortBy = "createdAt", sortOrder = "desc" } = options;

    const where: Record<string, unknown> = {};
    if (status) { where.status = Array.isArray(status) ? { in: status } : status; }
    if (priority) where.priority = priority;
    if (requesterId) where.requesterId = requesterId;
    if (type) where.type = type;
    if (targetResource) where.targetResource = { contains: targetResource };

    const [records, total] = await Promise.all([
      db.hitlApprovalRequest.findMany({ where, orderBy: { [sortBy]: sortOrder }, skip: (page - 1) * pageSize, take: pageSize }),
      db.hitlApprovalRequest.count({ where }),
    ]);

    return { data: records.map((r) => mapRecordToModel(r)), total, page, pageSize };
  }

  async approveRequest(requestId: string, input: ApproveRequestInput): Promise<ApprovalRequest> {
    const { updated, isFullyApproved, actualApprovalCount, requiredApprovals, recordTitle, recordPriority } = await db.$transaction(async (tx) => {
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
        data: { requestId, decision: DecisionType.APPROVED,
          decisionBy: input.decisionBy, decisionByName: input.decisionByName,
          role: input.role, comment: input.comment ?? "", delegatedFrom: input.delegatedFrom ?? null },
      });

      const policy: ApprovalPolicy = JSON.parse(record.approvalPolicy);
      const afterUpdate = await tx.hitlApprovalRequest.update({
        where: { requestId }, data: { currentApprovals: { increment: 1 } },
      });

      const actualApprovalCount = afterUpdate.currentApprovals;
      const isFullyApproved = isApprovalPolicySatisfied(policy, actualApprovalCount, record.requiredApprovals, []);

      const updated = isFullyApproved
        ? await tx.hitlApprovalRequest.update({ where: { requestId },
            data: { status: ApprovalRequestStatus.APPROVED, executedAt: new Date() } })
        : afterUpdate;

      return { updated, isFullyApproved, actualApprovalCount, requiredApprovals: record.requiredApprovals,
        recordTitle: record.title, recordPriority: record.priority as ApprovalPriority };
    });

    await recordAuditEvent({
      requestId, eventType: HitlEventType.APPROVED, actorId: input.decisionBy,
      actorName: input.decisionByName,
      details: { comment: input.comment, delegatedFrom: input.delegatedFrom,
        fullyApproved: isFullyApproved, currentApprovals: actualApprovalCount, requiredApprovals },
    });

    await notifyApprovalEvent(
      isFullyApproved ? "approval_approved" : "approval_pending",
      { requestId, title: recordTitle, priority: recordPriority,
        approverName: input.decisionByName, fullyApproved: isFullyApproved,
        currentApprovals: actualApprovalCount, requiredApprovals },
    );

    return mapRecordToModel(updated);
  }

  async rejectRequest(requestId: string, input: RejectRequestInput): Promise<ApprovalRequest> {
    const { updated, recordTitle, recordPriority, recordRequesterId } = await db.$transaction(async (tx) => {
      const record = await tx.hitlApprovalRequest.findUnique({ where: { requestId } });
      if (!record) throw new Error(`Approval request "${requestId}" not found`);
      if (record.status !== ApprovalRequestStatus.PENDING && record.status !== ApprovalRequestStatus.ESCALATED) {
        throw new Error(`Cannot reject request in status "${record.status}"`);
      }

      await tx.hitlApprovalDecision.create({
        data: { requestId, decision: DecisionType.REJECTED,
          decisionBy: input.decisionBy, decisionByName: input.decisionByName,
          role: input.role, comment: input.comment, delegatedFrom: null },
      });

      const updated = await tx.hitlApprovalRequest.update({
        where: { requestId }, data: { status: ApprovalRequestStatus.REJECTED },
      });

      return { updated, recordTitle: record.title, recordPriority: record.priority as ApprovalPriority,
        recordRequesterId: record.requesterId };
    });

    await recordAuditEvent({ requestId, eventType: HitlEventType.REJECTED,
      actorId: input.decisionBy, actorName: input.decisionByName,
      details: { comment: input.comment, role: input.role } });

    await notifyApprovalEvent("approval_rejected", {
      requestId, title: recordTitle, priority: recordPriority,
      rejecterName: input.decisionByName, reason: input.comment, requesterId: recordRequesterId });

    return mapRecordToModel(updated);
  }

  async updateRequest(requestId: string, updates: Partial<Pick<CreateApprovalRequestInput, "title" | "description" | "priority" | "deadline" | "tags" | "metadata">>): Promise<ApprovalRequest> {
    const record = await db.hitlApprovalRequest.findUnique({ where: { requestId } });
    if (!record) throw new Error(`Approval request "${requestId}" not found`);
    if (record.status !== ApprovalRequestStatus.PENDING) throw new Error(`Cannot update request in status "${record.status}"`);

    const data: Record<string, unknown> = {};
    if (updates.title !== undefined) data.title = updates.title;
    if (updates.description !== undefined) data.description = updates.description;
    if (updates.priority !== undefined) data.priority = updates.priority;
    if (updates.deadline !== undefined) data.deadline = updates.deadline ? new Date(updates.deadline) : null;
    if (updates.tags !== undefined) data.tags = JSON.stringify(updates.tags);
    if (updates.metadata !== undefined) data.metadata = JSON.stringify(updates.metadata);

    const updated = await db.hitlApprovalRequest.update({ where: { requestId }, data });
    return mapRecordToModel(updated);
  }

  async cancelRequest(requestId: string, cancelledBy: string, cancelledByName: string): Promise<ApprovalRequest> {
    const record = await db.hitlApprovalRequest.findUnique({ where: { requestId } });
    if (!record) throw new Error(`Approval request "${requestId}" not found`);
    if (record.status !== ApprovalRequestStatus.PENDING) throw new Error(`Cannot cancel request in status "${record.status}"`);

    const updated = await db.hitlApprovalRequest.update({
      where: { requestId }, data: { status: ApprovalRequestStatus.CANCELLED },
    });

    await recordAuditEvent({ requestId, eventType: HitlEventType.CANCELLED,
      actorId: cancelledBy, actorName: cancelledByName,
      details: { previousStatus: record.status } });

    return mapRecordToModel(updated);
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let engineInstance: ApprovalEngine | null = null;

export function getApprovalEngine(): ApprovalEngine {
  if (!engineInstance) engineInstance = ApprovalEngine.getInstance();
  return engineInstance;
}

export function resetApprovalEngine(): void {
  engineInstance = null;
  ApprovalEngine.instance = null;
}
