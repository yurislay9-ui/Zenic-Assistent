// ─── Zenic-Agents v3 — HITL Escalation Service ───────────────────────
// Phase 5: Auto-escalation, escalation chain management
//
// Design Patterns:
//   - Chain of Responsibility: Escalation chain handlers
//   - Observer: Notifies on escalation events

import { db } from "@/lib/db";
import {
  type EscalateRequestInput,
  type Escalation,
  ApprovalRequestStatus,
  HitlEventType,
  DEFAULT_ESCALATION_CHAIN,
} from "./types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";

// ═══════════════════════════════════════════════════════════════════════════
// Escalation Service (Chain of Responsibility Pattern)
// ═══════════════════════════════════════════════════════════════════════════

class EscalationService {
  private static instance: EscalationService | null = null;
  private escalationChain: typeof DEFAULT_ESCALATION_CHAIN;

  private constructor(escalationChain?: typeof DEFAULT_ESCALATION_CHAIN) {
    this.escalationChain = escalationChain ?? DEFAULT_ESCALATION_CHAIN;
  }

  static getInstance(): EscalationService {
    if (!EscalationService.instance) {
      EscalationService.instance = new EscalationService();
    }
    return EscalationService.instance;
  }

  /** Escalate an approval request to the next level */
  async escalateRequest(requestId: string, input: EscalateRequestInput): Promise<Escalation> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
      include: { escalations: true },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (record.status !== ApprovalRequestStatus.PENDING &&
        record.status !== ApprovalRequestStatus.DELEGATED &&
        record.status !== ApprovalRequestStatus.ESCALATED) {
      throw new Error(`Cannot escalate request in status "${record.status}"`);
    }

    const currentLevel = record.escalationLevel;
    const nextLevel = currentLevel + 1;

    // Check if we've exceeded the escalation chain
    const maxLevel = this.escalationChain.length - 1;
    if (nextLevel > maxLevel) {
      throw new Error(`Maximum escalation level (${maxLevel}) already reached`);
    }

    // Create the escalation record
    const escalation = await db.hitlEscalation.create({
      data: {
        requestId,
        fromLevel: currentLevel,
        toLevel: nextLevel,
        fromUserId: input.fromUserId ?? null,
        toUserId: input.toUserId ?? null,
        toRole: input.toRole,
        reason: input.reason ?? "",
        autoEscalated: false,
      },
    });

    // Update the request
    await db.hitlApprovalRequest.update({
      where: { requestId },
      data: {
        escalationLevel: nextLevel,
        status: ApprovalRequestStatus.ESCALATED,
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.ESCALATED,
      actorId: input.fromUserId ?? "system",
      actorName: input.fromUserId ? "User" : "System",
      details: {
        fromLevel: currentLevel,
        toLevel: nextLevel,
        toRole: input.toRole,
        reason: input.reason,
        autoEscalated: false,
      },
    });

    // Notify
    await notifyApprovalEvent("approval_escalated", {
      requestId,
      title: record.title,
      priority: record.priority,
      fromLevel: currentLevel,
      toLevel: nextLevel,
      toRole: input.toRole,
      reason: input.reason,
    });

    return this.mapEscalationRecord(escalation);
  }

  /** Check for requests that need auto-escalation based on timeout
   *  FIX #13: Añadido take con límite para evitar cargar todos los pendientes.
   */
  async checkAutoEscalation(): Promise<number> {
    const now = new Date();
    let escalatedCount = 0;

    // Find requests that are pending or already escalated and may need further escalation
    const candidates = await db.hitlApprovalRequest.findMany({
      where: {
        status: { in: [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.ESCALATED] },
      },
      include: { escalations: true },
      take: 100, // INVARIANT 3: max 100 por batch
    });

    for (const record of candidates) {
      const currentLevel = record.escalationLevel;
      const nextLevel = currentLevel + 1;

      // Check if next level exists in chain
      const nextLevelConfig = this.escalationChain.find((l) => l.level === nextLevel);
      if (!nextLevelConfig) continue;

      // Calculate timeout for current level
      const currentLevelConfig = this.escalationChain.find((l) => l.level === currentLevel);
      if (!currentLevelConfig || currentLevelConfig.timeoutMs === 0) continue;

      // Check if the timeout has elapsed
      const lastEscalation = record.escalations
        .filter((e) => e.toLevel === currentLevel)
        .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())[0];

      const referenceTime = lastEscalation
        ? lastEscalation.createdAt
        : record.createdAt;

      const elapsedMs = now.getTime() - referenceTime.getTime();

      if (elapsedMs >= currentLevelConfig.timeoutMs) {
        // Auto-escalate
        await db.hitlEscalation.create({
          data: {
            requestId: record.requestId,
            fromLevel: currentLevel,
            toLevel: nextLevel,
            fromUserId: null,
            toUserId: null,
            toRole: nextLevelConfig.role,
            reason: `Auto-escalated: no action within ${Math.round(currentLevelConfig.timeoutMs / 60000)} minutes`,
            autoEscalated: true,
          },
        });

        await db.hitlApprovalRequest.update({
          where: { requestId: record.requestId },
          data: {
            escalationLevel: nextLevel,
            status: ApprovalRequestStatus.ESCALATED,
          },
        });

        await recordAuditEvent({
          requestId: record.requestId,
          eventType: HitlEventType.ESCALATED,
          actorId: "system",
          actorName: "System",
          details: {
            fromLevel: currentLevel,
            toLevel: nextLevel,
            toRole: nextLevelConfig.role,
            autoEscalated: true,
            elapsedMs,
            timeoutMs: currentLevelConfig.timeoutMs,
          },
        });

        await notifyApprovalEvent("approval_escalated", {
          requestId: record.requestId,
          title: record.title,
          priority: record.priority,
          fromLevel: currentLevel,
          toLevel: nextLevel,
          toRole: nextLevelConfig.role,
          autoEscalated: true,
        });

        escalatedCount++;
      }
    }

    return escalatedCount;
  }

  /** Get escalation history for a request
   *  FIX #7: Añadido take con límite.
   */
  async getEscalationHistory(requestId: string, limit = 50): Promise<Escalation[]> {
    const escalations = await db.hitlEscalation.findMany({
      where: { requestId },
      orderBy: { createdAt: "asc" },
      take: Math.min(limit, 200), // INVARIANT 3
    });

    return escalations.map((e) => this.mapEscalationRecord(e));
  }

  private mapEscalationRecord(record: {
    id: string;
    requestId: string;
    fromLevel: number;
    toLevel: number;
    fromUserId: string | null;
    toUserId: string | null;
    toRole: string;
    reason: string;
    autoEscalated: boolean;
    createdAt: Date;
  }): Escalation {
    return {
      id: record.id,
      requestId: record.requestId,
      fromLevel: record.fromLevel,
      toLevel: record.toLevel,
      fromUserId: record.fromUserId,
      toUserId: record.toUserId,
      toRole: record.toRole,
      reason: record.reason,
      autoEscalated: record.autoEscalated,
      createdAt: record.createdAt.toISOString(),
    };
  }
}

// ─── Singleton Accessor ───────────────────────────────────────────────

let escalationServiceInstance: EscalationService | null = null;

export function getEscalationService(): EscalationService {
  if (!escalationServiceInstance) {
    escalationServiceInstance = EscalationService.getInstance();
  }
  return escalationServiceInstance;
}

export function resetEscalationService(): void {
  escalationServiceInstance = null;
}

export { EscalationService };
