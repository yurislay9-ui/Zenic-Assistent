// ─── Zenic-Agents v3 — HITL Approval Engine ────────────────────────────
// Phase 5: Core approval request lifecycle management
//
// Design Patterns:
//   - Singleton: Single engine instance via getApprovalEngine()
//   - Strategy: ApprovalPolicyStrategy for pluggable approval policies
//   - Observer: Emits events to NotificationService on state changes

import { db } from "@/lib/db";
import {
  type CreateApprovalRequestInput,
  type ApprovalRequest,
  type ApproveRequestInput,
  type RejectRequestInput,
  type ApprovalListOptions,
  type ApprovalPolicy,
  type ApprovalPolicyMode,
  type AutoApproveRule,
  type ApprovalStats,
  ApprovalRequestStatus,
  ApprovalPriority,
  ApprovalType,
  DecisionType,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";
import { notifyApprovalEvent } from "./notifications";

// ═══════════════════════════════════════════════════════════════════════════
// Strategy Pattern: Approval Policy Evaluator
// ═══════════════════════════════════════════════════════════════════════════

/** Evaluates whether an approval request can be auto-approved based on policy */
function evaluateAutoApproveRules(
  input: CreateApprovalRequestInput,
  rules: AutoApproveRule[],
): { canAutoApprove: boolean; matchedRule: string | null } {
  for (const rule of rules) {
    if (!rule.enabled) continue;

    const cond = rule.condition;

    // Check priority eligibility
    if (cond.allowedPriorities && cond.allowedPriorities.length > 0) {
      const priority = input.priority ?? ApprovalPriority.MEDIUM;
      if (!cond.allowedPriorities.includes(priority)) continue;
    }

    // Check action type eligibility
    if (cond.allowedActionTypes && cond.allowedActionTypes.length > 0) {
      if (!cond.allowedActionTypes.includes(input.type)) continue;
    }

    // Check required tags
    if (cond.requiredTags && cond.requiredTags.length > 0) {
      const tags = input.tags ?? [];
      const hasAll = cond.requiredTags.every((t) => tags.includes(t));
      if (!hasAll) continue;
    }

    // Check max affected resources
    if (cond.maxAffectedResources !== undefined) {
      const resources = input.actionPayload?.resources;
      if (Array.isArray(resources) && resources.length > cond.maxAffectedResources) continue;
    }

    // Check max amount
    if (cond.maxAmount !== undefined) {
      const amount = input.actionPayload?.amount;
      if (typeof amount === "number" && amount > cond.maxAmount) continue;
    }

    // Check risk score
    if (rule.maxRiskScore !== undefined) {
      const riskScore = input.actionPayload?.riskScore;
      if (typeof riskScore === "number" && riskScore > rule.maxRiskScore) continue;
    }

    // All conditions met
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
      return currentApprovals >= 1; // Auto-approve still requires at least one confirm

    default:
      return currentApprovals >= requiredApprovals;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ID Generation
// ═══════════════════════════════════════════════════════════════════════════

function generateRequestId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `hitl_${timestamp}_${random}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Approval Engine (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class ApprovalEngine {
  private static instance: ApprovalEngine | null = null;

  private constructor() {}

  static getInstance(): ApprovalEngine {
    if (!ApprovalEngine.instance) {
      ApprovalEngine.instance = new ApprovalEngine();
    }
    return ApprovalEngine.instance;
  }

  /** Create a new approval request */
  async createRequest(input: CreateApprovalRequestInput): Promise<ApprovalRequest> {
    const requestId = generateRequestId();
    const priority = input.priority ?? ApprovalPriority.MEDIUM;
    const policy: ApprovalPolicy = input.approvalPolicy ?? {
      mode: "single",
      defaultReversible: input.isReversible ?? true,
      undoWindowMs: input.undoWindowMs,
    };

    // Check auto-approve rules
    const autoApproveRules = policy.autoApproveRules ?? [];
    const { canAutoApprove, matchedRule } = evaluateAutoApproveRules(input, autoApproveRules);

    const isReversible = policy.defaultReversible ?? input.isReversible ?? true;
    const undoWindowMs = policy.undoWindowMs ?? input.undoWindowMs;
    const deadline = input.deadline ? new Date(input.deadline) : null;
    const undoDeadline = undoWindowMs
      ? new Date(Date.now() + undoWindowMs)
      : null;

    const initialStatus = canAutoApprove
      ? ApprovalRequestStatus.APPROVED
      : ApprovalRequestStatus.PENDING;

    const currentApprovals = canAutoApprove ? 1 : 0;
    const requiredApprovals = input.requiredApprovals ?? 1;

    // Create the request in the database
    const record = await db.hitlApprovalRequest.create({
      data: {
        requestId,
        title: input.title,
        description: input.description,
        type: input.type,
        status: initialStatus,
        priority,
        requesterId: input.requesterId,
        requesterName: input.requesterName,
        targetResource: input.targetResource,
        targetAction: input.targetAction,
        actionPayload: JSON.stringify(input.actionPayload ?? {}),
        undoPayload: JSON.stringify(input.undoPayload ?? {}),
        isReversible,
        undoDeadline,
        requiredApprovals,
        currentApprovals,
        approvalPolicy: JSON.stringify(policy),
        deadline,
        parentId: input.parentId ?? null,
        tags: JSON.stringify(input.tags ?? []),
        metadata: JSON.stringify(input.metadata ?? {}),
      },
    });

    // If auto-approved, create the auto-approve decision
    if (canAutoApprove) {
      await db.hitlApprovalDecision.create({
        data: {
          requestId: record.requestId,
          decision: DecisionType.APPROVED,
          decisionBy: "system",
          decisionByName: "System Auto-Approve",
          role: "system",
          comment: `Auto-approved by rule: ${matchedRule ?? "unknown"}`,
          delegatedFrom: null,
        },
      });
    }

    // Record audit event
    await recordAuditEvent({
      requestId: record.requestId,
      eventType: canAutoApprove ? HitlEventType.APPROVED : HitlEventType.CREATED,
      actorId: input.requesterId,
      actorName: input.requesterName,
      details: {
        title: input.title,
        type: input.type,
        priority,
        targetResource: input.targetResource,
        targetAction: input.targetAction,
        isReversible,
        autoApproved: canAutoApprove,
        autoApproveRule: matchedRule,
      },
    });

    // Send notifications
    await notifyApprovalEvent(
      canAutoApprove ? "approval_approved" : "approval_pending",
      {
        requestId: record.requestId,
        title: input.title,
        priority,
        requesterId: input.requesterId,
        requesterName: input.requesterName,
        autoApproved: canAutoApprove,
      },
    );

    return this.mapRecordToModel(record);
  }

  /** Get an approval request by ID */
  async getRequest(requestId: string): Promise<ApprovalRequest | null> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
      include: {
        decisions: true,
        delegations: true,
        escalations: true,
        undoActions: true,
      },
    });

    if (!record) return null;
    return this.mapRecordToModel(record);
  }

  /** List approval requests with filtering and pagination */
  async listRequests(options: ApprovalListOptions = {}): Promise<{
    data: ApprovalRequest[];
    total: number;
    page: number;
    pageSize: number;
  }> {
    const {
      status,
      priority,
      requesterId,
      type,
      targetResource,
      page = 1,
      pageSize = 20,
      sortBy = "createdAt",
      sortOrder = "desc",
    } = options;

    const where: Record<string, unknown> = {};

    if (status) {
      if (Array.isArray(status)) {
        where.status = { in: status };
      } else {
        where.status = status;
      }
    }

    if (priority) where.priority = priority;
    if (requesterId) where.requesterId = requesterId;
    if (type) where.type = type;
    if (targetResource) where.targetResource = { contains: targetResource };

    const [records, total] = await Promise.all([
      db.hitlApprovalRequest.findMany({
        where,
        orderBy: { [sortBy]: sortOrder },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.hitlApprovalRequest.count({ where }),
    ]);

    return {
      data: records.map((r) => this.mapRecordToModel(r)),
      total,
      page,
      pageSize,
    };
  }

  /** Approve a request — FIX: usa $transaction + atomic increment para evitar race condition */
  async approveRequest(requestId: string, input: ApproveRequestInput): Promise<ApprovalRequest> {
    // FIX #3: Toda la operación dentro de transacción para evitar race condition
    // en currentApprovals (read-modify-write sin tx = contador corrupto)
    const { updated, isFullyApproved, actualApprovalCount, requiredApprovals, recordTitle, recordPriority } = await db.$transaction(async (tx) => {
      const record = await tx.hitlApprovalRequest.findUnique({
        where: { requestId },
      });

      if (!record) {
        throw new Error(`Approval request "${requestId}" not found`);
      }

      if (record.status !== ApprovalRequestStatus.PENDING && record.status !== ApprovalRequestStatus.ESCALATED) {
        throw new Error(`Cannot approve request in status "${record.status}"`);
      }

      // Check for duplicate approval by same user
      const existingDecision = await tx.hitlApprovalDecision.findFirst({
        where: {
          requestId,
          decisionBy: input.decisionBy,
          decision: DecisionType.APPROVED,
        },
      });

      if (existingDecision) {
        throw new Error(`User "${input.decisionByName}" has already approved this request`);
      }

      // Create the approval decision
      await tx.hitlApprovalDecision.create({
        data: {
          requestId,
          decision: DecisionType.APPROVED,
          decisionBy: input.decisionBy,
          decisionByName: input.decisionByName,
          role: input.role,
          comment: input.comment ?? "",
          delegatedFrom: input.delegatedFrom ?? null,
        },
      });

      // FIX #5: Atomic increment + read back del valor actualizado.
      // Antes: newApprovalCount = record.currentApprovals + 1 (stale dentro de tx)
      // Ahora: actualizamos y leemos el valor real post-increment.
      const policy: ApprovalPolicy = JSON.parse(record.approvalPolicy);
      const afterUpdate = await tx.hitlApprovalRequest.update({
        where: { requestId },
        data: {
          currentApprovals: { increment: 1 }, // ATOMIC
        },
      });

      const actualApprovalCount = afterUpdate.currentApprovals;
      const isFullyApproved = isApprovalPolicySatisfied(
        policy,
        actualApprovalCount,
        record.requiredApprovals,
        [],
      );

      // Si fully approved, actualizar status y executedAt
      const updated = isFullyApproved
        ? await tx.hitlApprovalRequest.update({
            where: { requestId },
            data: {
              status: ApprovalRequestStatus.APPROVED,
              executedAt: new Date(),
            },
          })
        : afterUpdate;

      return {
        updated,
        isFullyApproved,
        actualApprovalCount,
        requiredApprovals: record.requiredApprovals,
        recordTitle: record.title,
        recordPriority: record.priority as ApprovalPriority,
      };
    });

    // Record audit (fuera de tx — best-effort)
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.APPROVED,
      actorId: input.decisionBy,
      actorName: input.decisionByName,
      details: {
        comment: input.comment,
        delegatedFrom: input.delegatedFrom,
        fullyApproved: isFullyApproved,
        currentApprovals: actualApprovalCount,
        requiredApprovals,
      },
    });

    // Notify
    await notifyApprovalEvent(
      isFullyApproved ? "approval_approved" : "approval_pending",
      {
        requestId,
        title: recordTitle,
        priority: recordPriority,
        approverName: input.decisionByName,
        fullyApproved: isFullyApproved,
        currentApprovals: actualApprovalCount,
        requiredApprovals,
      },
    );

    return this.mapRecordToModel(updated);
  }

  /** Reject a request
   *  FIX #4 ALTO: Antes hacía write-then-write sin transacción.
   *  Si fallaba entre create decision y update status, quedaba en estado inconsistente.
   *  Ahora toda la operación es atómica dentro de $transaction.
   */
  async rejectRequest(requestId: string, input: RejectRequestInput): Promise<ApprovalRequest> {
    const { updated, recordTitle, recordPriority, recordRequesterId } = await db.$transaction(async (tx) => {
      const record = await tx.hitlApprovalRequest.findUnique({
        where: { requestId },
      });

      if (!record) {
        throw new Error(`Approval request "${requestId}" not found`);
      }

      if (record.status !== ApprovalRequestStatus.PENDING && record.status !== ApprovalRequestStatus.ESCALATED) {
        throw new Error(`Cannot reject request in status "${record.status}"`);
      }

      // Create the rejection decision
      await tx.hitlApprovalDecision.create({
        data: {
          requestId,
          decision: DecisionType.REJECTED,
          decisionBy: input.decisionBy,
          decisionByName: input.decisionByName,
          role: input.role,
          comment: input.comment,
          delegatedFrom: null,
        },
      });

      const updated = await tx.hitlApprovalRequest.update({
        where: { requestId },
        data: {
          status: ApprovalRequestStatus.REJECTED,
        },
      });

      return {
        updated,
        recordTitle: record.title,
        recordPriority: record.priority as ApprovalPriority,
        recordRequesterId: record.requesterId,
      };
    });

    // Record audit (fuera de tx — best-effort)
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.REJECTED,
      actorId: input.decisionBy,
      actorName: input.decisionByName,
      details: {
        comment: input.comment,
        role: input.role,
      },
    });

    // Notify
    await notifyApprovalEvent("approval_rejected", {
      requestId,
      title: recordTitle,
      priority: recordPriority,
      rejecterName: input.decisionByName,
      reason: input.comment,
      requesterId: recordRequesterId,
    });

    return this.mapRecordToModel(updated);
  }

  /** Update a request (e.g., modify details before approval) */
  async updateRequest(
    requestId: string,
    updates: Partial<Pick<CreateApprovalRequestInput, "title" | "description" | "priority" | "deadline" | "tags" | "metadata">>,
  ): Promise<ApprovalRequest> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (record.status !== ApprovalRequestStatus.PENDING) {
      throw new Error(`Cannot update request in status "${record.status}"`);
    }

    const data: Record<string, unknown> = {};
    if (updates.title !== undefined) data.title = updates.title;
    if (updates.description !== undefined) data.description = updates.description;
    if (updates.priority !== undefined) data.priority = updates.priority;
    if (updates.deadline !== undefined) data.deadline = updates.deadline ? new Date(updates.deadline) : null;
    if (updates.tags !== undefined) data.tags = JSON.stringify(updates.tags);
    if (updates.metadata !== undefined) data.metadata = JSON.stringify(updates.metadata);

    const updated = await db.hitlApprovalRequest.update({
      where: { requestId },
      data,
    });

    return this.mapRecordToModel(updated);
  }

  /** Cancel a pending request */
  async cancelRequest(requestId: string, cancelledBy: string, cancelledByName: string): Promise<ApprovalRequest> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (record.status !== ApprovalRequestStatus.PENDING) {
      throw new Error(`Cannot cancel request in status "${record.status}"`);
    }

    const updated = await db.hitlApprovalRequest.update({
      where: { requestId },
      data: { status: ApprovalRequestStatus.CANCELLED },
    });

    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.CANCELLED,
      actorId: cancelledBy,
      actorName: cancelledByName,
      details: { previousStatus: record.status },
    });

    return this.mapRecordToModel(updated);
  }

  /** Check for expired requests and mark them — FIX: batch update + parallel audit/notify */
  async checkExpiredRequests(): Promise<number> {
    const now = new Date();
    const expired = await db.hitlApprovalRequest.findMany({
      where: {
        status: { in: [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.ESCALATED] },
        deadline: { not: null, lt: now },
      },
      take: 100, // INVARIANT 3: max 100 por batch
    });

    if (expired.length === 0) return 0;

    // FIX #6: Batch update + parallel side effects (antes era N×3 secuencial)
    // Paso 1: Batch update — 1 sola query con updateMany
    const expiredIds = expired.map((r) => r.requestId);
    await db.hitlApprovalRequest.updateMany({
      where: { requestId: { in: expiredIds } },
      data: { status: ApprovalRequestStatus.EXPIRED },
    });

    // Paso 2: Audit + Notify en paralelo por cada request
    await Promise.all(expired.map((record) =>
      Promise.all([
        recordAuditEvent({
          requestId: record.requestId,
          eventType: HitlEventType.EXPIRED,
          actorId: "system",
          actorName: "System",
          details: { deadline: record.deadline?.toISOString(), expiredAt: now.toISOString() },
        }),
        notifyApprovalEvent("approval_expired", {
          requestId: record.requestId,
          title: record.title,
          priority: record.priority as ApprovalPriority,
          requesterId: record.requesterId,
        }),
      ])
    ));

    return expired.length;
  }

  /** Get approval statistics — FIX: usa COUNT queries en vez de findMany(sin límite) */
  async getStats(): Promise<ApprovalStats> {
    // FIX #2: Antes cargaba TODOS los registros en memoria con findMany sin take.
    // El sistema de auditoría por diseño nunca elimina registros → crecimiento infinito.
    // Ahora: COUNT + GROUP BY en SQL → solo números, cero objetos en RAM.
    const [
      total,
      byStatusRows,
      byPriorityRows,
      byTypeRows,
      autoApprovedCount,
      avgDecisionRows,
    ] = await Promise.all([
      db.hitlApprovalRequest.count(),
      db.hitlApprovalRequest.groupBy({ by: ["status"], _count: { status: true } }),
      db.hitlApprovalRequest.groupBy({ by: ["priority"], _count: { priority: true } }),
      db.hitlApprovalRequest.groupBy({ by: ["type"], _count: { type: true } }),
      db.hitlApprovalDecision.count({
        where: { decisionBy: "system", decision: DecisionType.APPROVED },
      }),
      // Avg decision time: solo approved/rejected con updatedAt-createdAt
      db.hitlApprovalRequest.findMany({
        where: {
          status: { in: [ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED] },
        },
        select: { createdAt: true, updatedAt: true },
        take: 200, // INVARIANT 3: muestra representativa, no toda la tabla
        orderBy: { createdAt: "desc" },
      }),
    ]);

    const byStatus: Record<string, number> = {};
    for (const row of byStatusRows) {
      byStatus[row.status] = row._count.status;
    }

    const byPriority: Record<string, number> = {};
    for (const row of byPriorityRows) {
      byPriority[row.priority] = row._count.priority;
    }

    const byType: Record<string, number> = {};
    for (const row of byTypeRows) {
      byType[row.type] = row._count.type;
    }

    const totalDecisionTime = avgDecisionRows.reduce(
      (sum, r) => sum + (new Date(r.updatedAt).getTime() - new Date(r.createdAt).getTime()),
      0,
    );
    const decisionCount = avgDecisionRows.length;

    const undone = byStatus[ApprovalRequestStatus.UNDONE] ?? 0;
    const delegated = byStatus[ApprovalRequestStatus.DELEGATED] ?? 0;
    const escalated = byStatus[ApprovalRequestStatus.ESCALATED] ?? 0;

    return {
      total,
      byStatus: byStatus as Record<ApprovalRequestStatus, number>,
      byPriority: byPriority as Record<ApprovalPriority, number>,
      byType: byType as Record<ApprovalType, number>,
      avgTimeToDecision: decisionCount > 0 ? Math.round(totalDecisionTime / decisionCount) : 0,
      avgTimeToExecution: 0,
      undoRate: total > 0 ? undone / total : 0,
      autoApproveRate: total > 0 ? autoApprovedCount / total : 0,
      delegationRate: total > 0 ? delegated / total : 0,
      escalationRate: total > 0 ? escalated / total : 0,
    };
  }

  /** List pending approvals for a specific user — FIX: filtra en SQL, no en JS */
  async listPendingForUser(userId: string): Promise<ApprovalRequest[]> {
    // FIX #8: Antes cargaba TODAS las pendientes y filtraba en JS.
    // Ahora: obtiene IDs decididos → excluye en SQL con NOT requestId IN (...)
    // e incluye delegadas con OR requestId IN (delegated).

    const [decidedIds, delegatedIds] = await Promise.all([
      db.hitlApprovalDecision.findMany({
        where: { decisionBy: userId },
        select: { requestId: true },
      }),
      db.hitlDelegation.findMany({
        where: { toUserId: userId, isActive: true },
        select: { requestId: true },
      }),
    ]);

    const decidedRequestIds = decidedIds.map((d) => d.requestId);
    const delegatedRequestIds = delegatedIds.map((d) => d.requestId);

    // Pending where user hasn't decided, OR where user has an active delegation
    const pendingRequests = await db.hitlApprovalRequest.findMany({
      where: {
        status: { in: [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.ESCALATED] },
        OR: [
          { requestId: { notIn: decidedRequestIds } },
          { requestId: { in: delegatedRequestIds } },
        ],
      },
      orderBy: { createdAt: "desc" },
      take: 100, // INVARIANT 3
    });

    return pendingRequests.map((r) => this.mapRecordToModel(r));
  }

  /** Get approval history with filters */
  async getHistory(options: ApprovalListOptions & { userId?: string }): Promise<{
    data: ApprovalRequest[];
    total: number;
    page: number;
    pageSize: number;
  }> {
    const {
      status,
      priority,
      requesterId,
      type,
      targetResource,
      userId,
      page = 1,
      pageSize = 20,
      sortBy = "createdAt",
      sortOrder = "desc",
    } = options;

    const where: Record<string, unknown> = {};

    // Only show completed/closed statuses in history
    if (!status) {
      where.status = {
        in: [
          ApprovalRequestStatus.APPROVED,
          ApprovalRequestStatus.REJECTED,
          ApprovalRequestStatus.EXPIRED,
          ApprovalRequestStatus.UNDONE,
          ApprovalRequestStatus.CANCELLED,
        ],
      };
    } else {
      if (Array.isArray(status)) {
        where.status = { in: status };
      } else {
        where.status = status;
      }
    }

    if (priority) where.priority = priority;
    if (requesterId) where.requesterId = requesterId;
    if (type) where.type = type;
    if (targetResource) where.targetResource = { contains: targetResource };

    // If userId is specified, filter to requests where user was involved
    if (userId) {
      const decisions = await db.hitlApprovalDecision.findMany({
        where: { decisionBy: userId },
        select: { requestId: true },
      });
      const delegations = await db.hitlDelegation.findMany({
        where: {
          OR: [{ fromUserId: userId }, { toUserId: userId }],
        },
        select: { requestId: true },
      });

      const involvedIds = new Set([
        ...decisions.map((d) => d.requestId),
        ...delegations.map((d) => d.requestId),
      ]);

      where.requestId = { in: Array.from(involvedIds) };
    }

    const [records, total] = await Promise.all([
      db.hitlApprovalRequest.findMany({
        where,
        orderBy: { [sortBy]: sortOrder },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.hitlApprovalRequest.count({ where }),
    ]);

    return {
      data: records.map((r) => this.mapRecordToModel(r)),
      total,
      page,
      pageSize,
    };
  }

  /** Map a database record to the domain model */
  private mapRecordToModel(record: {
    id: string;
    requestId: string;
    title: string;
    description: string;
    type: string;
    status: string;
    priority: string;
    requesterId: string;
    requesterName: string;
    targetResource: string;
    targetAction: string;
    actionPayload: string;
    undoPayload: string;
    isReversible: boolean;
    undoDeadline: Date | null;
    undoExecutedAt: Date | null;
    executedAt: Date | null;
    executionResult: string | null;
    requiredApprovals: number;
    currentApprovals: number;
    approvalPolicy: string;
    deadline: Date | null;
    escalationLevel: number;
    parentId: string | null;
    tags: string;
    metadata: string;
    createdAt: Date;
    updatedAt: Date;
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
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let engineInstance: ApprovalEngine | null = null;

export function getApprovalEngine(): ApprovalEngine {
  if (!engineInstance) {
    engineInstance = ApprovalEngine.getInstance();
  }
  return engineInstance;
}

export function resetApprovalEngine(): void {
  engineInstance = null;
  ApprovalEngine.instance = null; // FIX #5: también limpia static instance
}

// Re-export strategy function for external use
export { evaluateAutoApproveRules, isApprovalPolicySatisfied };
