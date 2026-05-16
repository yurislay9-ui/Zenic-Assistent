// ─── Zenic-Agents MCP Gateway — Audit Service (Prisma-backed) ─────────
// Functional audit service used by API routes for recording audit entries.
// Persists audit logs to the database via Prisma.

import { db } from "@/lib/db";

/** Audit record parameters */
export interface AuditRecordParams {
  action: string;
  resource: string;
  resourceId?: string;
  resourceName?: string;
  actorId?: string;
  actorType?: "user" | "system" | "service" | "agent";
  severity?: "debug" | "info" | "warn" | "error" | "critical";
  outcome?: "success" | "failure" | "denied" | "error";
  details?: Record<string, unknown>;
  ipAddress?: string;
  userAgent?: string;
  sessionId?: string;
  traceId?: string;
  tags?: string[];
}

/**
 * Record a single audit entry to the database.
 */
export async function recordAudit(params: AuditRecordParams): Promise<void> {
  try {
    // Only set actorId FK when actorType is "user" (real user reference)
    // For system/service/agent actors, set actorId: null and preserve
    // the original ID in details._actorId for traceability
    const isUserActor = params.actorType === "user";
    const actorId = isUserActor ? params.actorId : null;

    await db.auditLog.create({
      data: {
        actorId,
        actorType: params.actorType ?? "system",
        action: params.action,
        resource: params.resource,
        resourceId: params.resourceId,
        resourceName: params.resourceName,
        severity: params.severity ?? "info",
        outcome: params.outcome ?? "success",
        details: JSON.stringify({
          ...params.details,
          // Preserve original actor ID for non-user actors
          ...(!isUserActor && params.actorId ? { _actorId: params.actorId } : {}),
        }),
        ipAddress: params.ipAddress,
        userAgent: params.userAgent,
        sessionId: params.sessionId,
        traceId: params.traceId,
        tags: JSON.stringify(params.tags ?? []),
      },
    });
  } catch (error) {
    // Audit logging should never fail the main operation
    console.error("[recordAudit] Failed to record audit entry:", error);
  }
}

/**
 * Record multiple audit entries in batch.
 */
export async function recordAuditBatch(entries: AuditRecordParams[]): Promise<void> {
  try {
    await db.auditLog.createMany({
      data: entries.map((params) => {
        const isUserActor = params.actorType === "user";
        const actorId = isUserActor ? params.actorId : null;

        return {
          actorId,
          actorType: params.actorType ?? "system",
          action: params.action,
          resource: params.resource,
          resourceId: params.resourceId,
          resourceName: params.resourceName,
          severity: params.severity ?? "info",
          outcome: params.outcome ?? "success",
          details: JSON.stringify({
            ...params.details,
            ...(!isUserActor && params.actorId ? { _actorId: params.actorId } : {}),
          }),
          ipAddress: params.ipAddress,
          userAgent: params.userAgent,
          sessionId: params.sessionId,
          traceId: params.traceId,
          tags: JSON.stringify(params.tags ?? []),
        };
      }),
    });
  } catch (error) {
    console.error("[recordAuditBatch] Failed to record audit batch:", error);
  }
}
