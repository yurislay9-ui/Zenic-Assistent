// ─── Zenic-Agents v3 — HITL Approval Engine: Internal Types & Queries
// Shared DB record type, record-to-model mapper, and read-only query functions.

import { db } from "@/lib/db";
import {
  type ApprovalRequest,
  type ApprovalListOptions,
  type ApprovalStats,
  ApprovalRequestStatus,
  ApprovalPriority,
  ApprovalType,
  DecisionType,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";

// ═══════════════════════════════════════════════════════════════════════════
// DB Record Type & Mapper
// ═══════════════════════════════════════════════════════════════════════════

/** Database record shape returned by Prisma queries */
export interface DbApprovalRecord {
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
}

/** Map a database record to the domain model */
export function mapDbRecordToModel(record: DbApprovalRecord): ApprovalRequest {
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

// ═══════════════════════════════════════════════════════════════════════════
// Query Functions (read-only operations)
// ═══════════════════════════════════════════════════════════════════════════

/** Get a single approval request by ID */
export async function queryGetRequest(requestId: string): Promise<ApprovalRequest | null> {
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
  return mapDbRecordToModel(record as unknown as DbApprovalRecord);
}

/** List approval requests with filtering and pagination */
export async function queryListRequests(options: ApprovalListOptions = {}): Promise<{
  data: ApprovalRequest[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const {
    status, priority, requesterId, type, targetResource,
    page = 1, pageSize = 20, sortBy = "createdAt", sortOrder = "desc",
  } = options;

  const where: Record<string, unknown> = {};
  if (status) {
    where.status = Array.isArray(status) ? { in: status } : status;
  }
  if (priority) where.priority = priority;
  if (requesterId) where.requesterId = requesterId;
  if (type) where.type = type;
  if (targetResource) where.targetResource = { contains: targetResource };

  const [records, total] = await Promise.all([
    db.hitlApprovalRequest.findMany({
      where, orderBy: { [sortBy]: sortOrder },
      skip: (page - 1) * pageSize, take: pageSize,
    }),
    db.hitlApprovalRequest.count({ where }),
  ]);

  return {
    data: records.map((r) => mapDbRecordToModel(r as unknown as DbApprovalRecord)),
    total, page, pageSize,
  };
}

/** Check for expired requests and mark them — batch update + parallel audit/notify */
export async function queryCheckExpiredRequests(): Promise<number> {
  const now = new Date();
  const expired = await db.hitlApprovalRequest.findMany({
    where: {
      status: { in: [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.ESCALATED] },
      deadline: { not: null, lt: now },
    },
    take: 100,
  });
  if (expired.length === 0) return 0;

  const expiredIds = expired.map((r) => r.requestId);
  await db.hitlApprovalRequest.updateMany({
    where: { requestId: { in: expiredIds } },
    data: { status: ApprovalRequestStatus.EXPIRED },
  });

  await Promise.all(expired.map((record) =>
    Promise.all([
      recordAuditEvent({
        requestId: record.requestId,
        eventType: HitlEventType.EXPIRED,
        actorId: "system", actorName: "System",
        details: { deadline: record.deadline?.toISOString(), expiredAt: now.toISOString() },
      }),
      notifyApprovalEvent("approval_expired", {
        requestId: record.requestId, title: record.title,
        priority: record.priority as ApprovalPriority,
        requesterId: record.requesterId,
      }),
    ])
  ));

  return expired.length;
}

/** Get approval statistics — uses COUNT queries instead of findMany without limit */
export async function queryGetStats(): Promise<ApprovalStats> {
  const [total, byStatusRows, byPriorityRows, byTypeRows, autoApprovedCount, avgDecisionRows] =
    await Promise.all([
      db.hitlApprovalRequest.count(),
      db.hitlApprovalRequest.groupBy({ by: ["status"], _count: { status: true } }),
      db.hitlApprovalRequest.groupBy({ by: ["priority"], _count: { priority: true } }),
      db.hitlApprovalRequest.groupBy({ by: ["type"], _count: { type: true } }),
      db.hitlApprovalDecision.count({
        where: { decisionBy: "system", decision: DecisionType.APPROVED },
      }),
      db.hitlApprovalRequest.findMany({
        where: { status: { in: [ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED] } },
        select: { createdAt: true, updatedAt: true },
        take: 200, orderBy: { createdAt: "desc" },
      }),
    ]);

  const byStatus: Record<string, number> = {};
  for (const row of byStatusRows) byStatus[row.status] = row._count.status;
  const byPriority: Record<string, number> = {};
  for (const row of byPriorityRows) byPriority[row.priority] = row._count.priority;
  const byType: Record<string, number> = {};
  for (const row of byTypeRows) byType[row.type] = row._count.type;

  const totalDecisionTime = avgDecisionRows.reduce(
    (sum, r) => sum + (new Date(r.updatedAt).getTime() - new Date(r.createdAt).getTime()), 0,
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

/** List pending approvals for a specific user — filters in SQL */
export async function queryListPendingForUser(userId: string): Promise<ApprovalRequest[]> {
  const [decidedIds, delegatedIds] = await Promise.all([
    db.hitlApprovalDecision.findMany({
      where: { decisionBy: userId }, select: { requestId: true },
    }),
    db.hitlDelegation.findMany({
      where: { toUserId: userId, isActive: true }, select: { requestId: true },
    }),
  ]);

  const decidedRequestIds = decidedIds.map((d) => d.requestId);
  const delegatedRequestIds = delegatedIds.map((d) => d.requestId);

  const pendingRequests = await db.hitlApprovalRequest.findMany({
    where: {
      status: { in: [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.ESCALATED] },
      OR: [
        { requestId: { notIn: decidedRequestIds } },
        { requestId: { in: delegatedRequestIds } },
      ],
    },
    orderBy: { createdAt: "desc" }, take: 100,
  });
  return pendingRequests.map((r) => mapDbRecordToModel(r as unknown as DbApprovalRecord));
}

/** Get approval history with filters */
export async function queryGetHistory(options: ApprovalListOptions & { userId?: string }): Promise<{
  data: ApprovalRequest[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const {
    status, priority, requesterId, type, targetResource, userId,
    page = 1, pageSize = 20, sortBy = "createdAt", sortOrder = "desc",
  } = options;

  const where: Record<string, unknown> = {};
  if (!status) {
    where.status = {
      in: [ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED,
        ApprovalRequestStatus.EXPIRED, ApprovalRequestStatus.UNDONE, ApprovalRequestStatus.CANCELLED],
    };
  } else {
    where.status = Array.isArray(status) ? { in: status } : status;
  }

  if (priority) where.priority = priority;
  if (requesterId) where.requesterId = requesterId;
  if (type) where.type = type;
  if (targetResource) where.targetResource = { contains: targetResource };

  if (userId) {
    const [decisions, delegations] = await Promise.all([
      db.hitlApprovalDecision.findMany({ where: { decisionBy: userId }, select: { requestId: true } }),
      db.hitlDelegation.findMany({
        where: { OR: [{ fromUserId: userId }, { toUserId: userId }] },
        select: { requestId: true },
      }),
    ]);
    const involvedIds = new Set([...decisions.map((d) => d.requestId), ...delegations.map((d) => d.requestId)]);
    where.requestId = { in: Array.from(involvedIds) };
  }

  const [records, total] = await Promise.all([
    db.hitlApprovalRequest.findMany({
      where, orderBy: { [sortBy]: sortOrder },
      skip: (page - 1) * pageSize, take: pageSize,
    }),
    db.hitlApprovalRequest.count({ where }),
  ]);

  return {
    data: records.map((r) => mapDbRecordToModel(r as unknown as DbApprovalRecord)),
    total, page, pageSize,
  };
}
