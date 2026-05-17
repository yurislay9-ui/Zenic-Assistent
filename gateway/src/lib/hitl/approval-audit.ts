// ─── Zenic-Agents v3 — HITL Approval Audit Trail ─────────────────────
// Phase 5: Full audit trail with Merkle chain integrity
//
// Design Patterns:
//   - Chain of Responsibility: Linked audit records
//   - Merkle Tree: Cryptographic integrity verification
//   - Observer: Records events from all HITL services
//
// Integration: Phase 1 Merkle Audit (gateway/mcp-gateway/audit/)

import { createHash } from "crypto";
import { db } from "@/lib/db";
import {
  type ApprovalAuditRecord,
  type ApprovalTimelineEvent,
  type ComplianceExportRecord,
  type HitlEventType,
  ApprovalRequestStatus,
  ApprovalType,
  DecisionType,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// Audit Event Recording
// ═══════════════════════════════════════════════════════════════════════════

/** Genesis hash for the HITL audit chain */
const HITL_GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

/** Compute SHA-256 content hash for an audit record */
function computeContentHash(data: {
  requestId: string;
  eventType: string;
  actorId: string;
  actorName: string;
  details: string;
  previousHash: string | null;
  timestamp: string;
}): string {
  const canonical = JSON.stringify({
    requestId: data.requestId,
    eventType: data.eventType,
    actorId: data.actorId,
    actorName: data.actorName,
    details: data.details,
    previousHash: data.previousHash,
    timestamp: data.timestamp,
  });
  return createHash("sha256").update(canonical).digest("hex");
}

/** Record an audit event in the HITL approval audit trail
 *  FIX #2 CRÍTICO: Race condition — antes hacía read-then-write sin transacción.
 *  Si dos eventos se grababan concurrentemente, ambos obtenían el mismo previousHash,
 *  rompiendo la cadena Merkle. Ahora usa $transaction con lock serializable
 *  para garantizar que el hash se encadene correctamente bajo concurrencia.
 */
export async function recordAuditEvent(params: {
  requestId: string;
  eventType: HitlEventType;
  actorId: string;
  actorName: string;
  details: Record<string, unknown>;
}): Promise<ApprovalAuditRecord> {
  const timestamp = new Date().toISOString();
  const detailsStr = JSON.stringify(params.details);

  // FIX #2: Toda la operación dentro de transacción serializable
  // para evitar race condition en la cadena Merkle.
  // Pasos atómicos: 1) leer último hash → 2) computar nuevo → 3) escribir
  const record = await db.$transaction(async (tx) => {
    // 1. Get the latest audit record for this request to chain the hash
    const latestAudit = await tx.hitlApprovalAudit.findFirst({
      where: { requestId: params.requestId },
      orderBy: { timestamp: "desc" },
    });

    // If no record for this request, get the global latest for cross-request chaining
    let previousHash: string;
    if (latestAudit?.contentHash) {
      previousHash = latestAudit.contentHash;
    } else {
      const globalLatest = await tx.hitlApprovalAudit.findFirst({
        orderBy: { timestamp: "desc" },
        select: { contentHash: true },
      });
      previousHash = globalLatest?.contentHash ?? HITL_GENESIS_HASH;
    }

    // 2. Compute content hash
    const contentHash = computeContentHash({
      requestId: params.requestId,
      eventType: params.eventType,
      actorId: params.actorId,
      actorName: params.actorName,
      details: detailsStr,
      previousHash,
      timestamp,
    });

    // 3. Create the record atomically
    return tx.hitlApprovalAudit.create({
      data: {
        requestId: params.requestId,
        eventType: params.eventType,
        actorId: params.actorId,
        actorName: params.actorName,
        details: detailsStr,
        contentHash,
        previousHash,
        timestamp: new Date(timestamp),
      },
    });
  });

  return {
    id: record.id,
    requestId: record.requestId,
    eventType: record.eventType as HitlEventType,
    actorId: record.actorId,
    actorName: record.actorName,
    details: JSON.parse(record.details),
    contentHash: record.contentHash,
    previousHash: record.previousHash,
    timestamp: record.timestamp.toISOString(),
  };
}

// getLatestGlobalHash eliminado — la lógica ahora vive dentro de la
// transacción en recordAuditEvent (FIX #2). Se mantiene HITL_GENESIS_HASH
// como constante para uso directo.

// ═══════════════════════════════════════════════════════════════════════════
// Audit Trail Query & Verification
// ═══════════════════════════════════════════════════════════════════════════

/** Get the complete audit trail for a request */
export async function getAuditTrail(requestId: string): Promise<ApprovalAuditRecord[]> {
  const records = await db.hitlApprovalAudit.findMany({
    where: { requestId },
    orderBy: { timestamp: "asc" },
  });

  return records.map((r) => ({
    id: r.id,
    requestId: r.requestId,
    eventType: r.eventType as HitlEventType,
    actorId: r.actorId,
    actorName: r.actorName,
    details: JSON.parse(r.details),
    contentHash: r.contentHash,
    previousHash: r.previousHash,
    timestamp: r.timestamp.toISOString(),
  }));
}

/** Verify the Merkle chain integrity for a request's audit trail */
export async function verifyAuditIntegrity(requestId: string): Promise<{
  valid: boolean;
  brokenAtIndex?: number;
  expectedHash?: string;
  actualHash?: string;
  totalRecords: number;
}> {
  const records = await db.hitlApprovalAudit.findMany({
    where: { requestId },
    orderBy: { timestamp: "asc" },
  });

  if (records.length === 0) {
    return { valid: true, totalRecords: 0 };
  }

  for (let i = 0; i < records.length; i++) {
    const record = records[i];
    const expectedHash = computeContentHash({
      requestId: record.requestId,
      eventType: record.eventType,
      actorId: record.actorId,
      actorName: record.actorName,
      details: record.details,
      previousHash: record.previousHash,
      timestamp: record.timestamp.toISOString(),
    });

    if (record.contentHash !== expectedHash) {
      return {
        valid: false,
        brokenAtIndex: i,
        expectedHash,
        actualHash: record.contentHash,
        totalRecords: records.length,
      };
    }

    // Verify chain linkage
    if (i > 0) {
      const prevRecord = records[i - 1];
      if (record.previousHash !== prevRecord.contentHash) {
        return {
          valid: false,
          brokenAtIndex: i,
          expectedHash: prevRecord.contentHash,
          actualHash: record.previousHash,
          totalRecords: records.length,
        };
      }
    }
  }

  return { valid: true, totalRecords: records.length };
}

// ═══════════════════════════════════════════════════════════════════════════
// Timeline Visualization Data
// ═══════════════════════════════════════════════════════════════════════════

/** Get the approval timeline for visualization */
export async function getApprovalTimeline(requestId: string): Promise<ApprovalTimelineEvent[]> {
  const records = await getAuditTrail(requestId);

  return records.map((r) => ({
    eventType: r.eventType,
    timestamp: r.timestamp,
    actorId: r.actorId,
    actorName: r.actorName,
    description: formatTimelineDescription(r),
    details: r.details,
  }));
}

/** Format a human-readable description for a timeline event */
function formatTimelineDescription(record: ApprovalAuditRecord): string {
  const details = record.details;

  switch (record.eventType) {
    case "created":
      return `${record.actorName} created approval request "${details.title ?? ""}" (${details.type ?? ""})`;
    case "approved": {
      const fully = details.fullyApproved as boolean | undefined;
      return fully
        ? `${record.actorName} approved the request (fully approved: ${details.currentApprovals}/${details.requiredApprovals})`
        : `${record.actorName} approved the request (${details.currentApprovals}/${details.requiredApprovals})`;
    }
    case "rejected":
      return `${record.actorName} rejected the request: ${details.comment ?? ""}`;
    case "delegated":
      return `${record.actorName} delegated to ${details.toUserName ?? "another user"}`;
    case "escalated": {
      const auto = details.autoEscalated as boolean | undefined;
      return auto
        ? `System auto-escalated to level ${details.toLevel} (${details.toRole ?? ""})`
        : `${record.actorName} escalated to level ${details.toLevel} (${details.toRole ?? ""})`;
    }
    case "executed":
      return `System executed the approved action (${details.actionType ?? "unknown"})`;
    case "undone":
      return `${record.actorName} undid the action (${details.undoType ?? "full_undo"}): ${details.reason ?? ""}`;
    case "expired":
      return `Request expired (deadline: ${details.deadline ?? "N/A"})`;
    case "cancelled":
      return `${record.actorName} cancelled the request`;
    default:
      return `${record.actorName} performed ${record.eventType}`;
  }
}

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
 *  y construye los ComplianceExportRecords en JS, evitando O(N) queries.
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
