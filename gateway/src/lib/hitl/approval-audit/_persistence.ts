// ─── Zenic-Agents v3 — HITL Approval Audit Persistence ───────────────
// Compliance export and batch operations for approval audit records.

import { createHash } from "crypto";
import { db } from "@/lib/db";
import {
  type ComplianceExportRecord,
  ApprovalRequestStatus,
  ApprovalType,
  DecisionType,
} from "../types";

// ═══════════════════════════════════════════════════════════════════════════
// Compliance Export
// ═══════════════════════════════════════════════════════════════════════════

/** Export a compliance-ready record for a request */
export async function exportComplianceRecord(requestId: string): Promise<ComplianceExportRecord | null> {
  const request = await db.hitlApprovalRequest.findUnique({
    where: { requestId },
    include: {
      decisions: true,
      delegations: true,
      escalations: true,
      undoActions: true,
      auditRecords: { orderBy: { timestamp: "asc" } },
    },
  });

  if (!request) return null;

  // Compute integrity hash from the audit trail
  const auditHashes = request.auditRecords.map((a) => a.contentHash);
  const integrityHash = createHash("sha256")
    .update(JSON.stringify(auditHashes))
    .digest("hex");

  const approvers = request.decisions.map((d) => ({
    name: d.decisionByName,
    role: d.role,
    decision: d.decision as DecisionType,
    decidedAt: d.decidedAt.toISOString(),
    comment: d.comment,
  }));

  const delegations = request.delegations.map((d) => ({
    from: d.fromUserName,
    to: d.toUserName,
    reason: d.reason,
    createdAt: d.createdAt.toISOString(),
  }));

  const escalations = request.escalations.map((e) => ({
    fromLevel: e.fromLevel,
    toLevel: e.toLevel,
    toRole: e.toRole,
    reason: e.reason,
    createdAt: e.createdAt.toISOString(),
  }));

  const lastUndo = request.undoActions[request.undoActions.length - 1];

  return {
    requestId: request.requestId,
    title: request.title,
    type: request.type as ApprovalType, // FIX #10: era ApprovalRequestStatus, debe ser ApprovalType
    status: request.status as ApprovalRequestStatus,
    requester: request.requesterName,
    approvers,
    delegations,
    escalations,
    executedAt: request.executedAt?.toISOString() ?? null,
    undo: {
      executedAt: lastUndo?.executedAt?.toISOString() ?? null,
      undoBy: lastUndo?.undoByName ?? null,
      reason: lastUndo?.reason ?? null,
    },
    createdAt: request.createdAt.toISOString(),
    integrityHash,
  };
}

/** Batch export compliance records for multiple requests
 *  FIX #6: Antes hacía N+1 queries (1 por cada requestId).
 *  Ahora carga todos los requests con includes en 1 sola query
 *  y construye los ComplianceExportRecords en js, evitando O(N) queries.
 */
export async function batchExportComplianceRecords(options?: {
  status?: ApprovalRequestStatus;
  startDate?: string;
  endDate?: string;
  limit?: number;
}): Promise<ComplianceExportRecord[]> {
  const where: Record<string, unknown> = {};

  if (options?.status) where.status = options.status;
  if (options?.startDate || options?.endDate) {
    where.createdAt = {
      ...(options.startDate ? { gte: new Date(options.startDate) } : {}),
      ...(options.endDate ? { lte: new Date(options.endDate) } : {}),
    };
  }

  const BATCH_LIMIT = Math.min(options?.limit ?? 100, 200); // INVARIANT 3

  // FIX #6: Una sola query con includes en vez de N+1
  const requests = await db.hitlApprovalRequest.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: BATCH_LIMIT,
    include: {
      decisions: true,
      delegations: true,
      escalations: true,
      undoActions: { orderBy: { createdAt: "asc" } },
      auditRecords: { orderBy: { timestamp: "asc" } },
    },
  });

  // Construir ComplianceExportRecords desde los datos ya cargados
  return requests.map((request) => {
    const auditHashes = request.auditRecords.map((a) => a.contentHash);
    const integrityHash = createHash("sha256")
      .update(JSON.stringify(auditHashes))
      .digest("hex");

    const approvers = request.decisions.map((d) => ({
      name: d.decisionByName,
      role: d.role,
      decision: d.decision as DecisionType,
      decidedAt: d.decidedAt.toISOString(),
      comment: d.comment,
    }));

    const delegations = request.delegations.map((d) => ({
      from: d.fromUserName,
      to: d.toUserName,
      reason: d.reason,
      createdAt: d.createdAt.toISOString(),
    }));

    const escalations = request.escalations.map((e) => ({
      fromLevel: e.fromLevel,
      toLevel: e.toLevel,
      toRole: e.toRole,
      reason: e.reason,
      createdAt: e.createdAt.toISOString(),
    }));

    const lastUndo = request.undoActions[request.undoActions.length - 1];

    return {
      requestId: request.requestId,
      title: request.title,
      type: request.type as ApprovalType,
      status: request.status as ApprovalRequestStatus,
      requester: request.requesterName,
      approvers,
      delegations,
      escalations,
      executedAt: request.executedAt?.toISOString() ?? null,
      undo: {
        executedAt: lastUndo?.executedAt?.toISOString() ?? null,
        undoBy: lastUndo?.undoByName ?? null,
        reason: lastUndo?.reason ?? null,
      },
      createdAt: request.createdAt.toISOString(),
      integrityHash,
    };
  });
}
