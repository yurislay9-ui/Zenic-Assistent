// ─── Zenic-Agents v3 — HITL Escalation SLA Service ───────────────────
// Phase 5: SLA-based escalation for approval requests
//
// Design Patterns:
//   - Singleton: Single service instance via getSLAService()
//   - Chain of Responsibility: Escalation level chain
//   - Observer: Records audit events, triggers notifications
//   - Integration: Uses EscalationService for actual escalation,
//     NotificationService for notifications

import { db } from "@/lib/db";
import {
  type EscalationSLA,
  ApprovalRequestStatus,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";
import { notifyApprovalEvent } from "./notifications";
import { getEscalationService } from "./delegation";

// ═══════════════════════════════════════════════════════════════════════════
// ID Generation
// ═══════════════════════════════════════════════════════════════════════════

function generateSLAId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `sla_${timestamp}_${random}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Default SLA Policies
// ═══════════════════════════════════════════════════════════════════════════

interface SLALevelPolicy {
  /** Escalation level (0-3) */
  level: number;
  /** Target role for this level */
  targetRole: string;
  /** SLA deadline in minutes */
  deadlineMinutes: number;
  /** Whether to auto-escalate on breach */
  autoEscalate: boolean;
}

const DEFAULT_SLA_POLICIES: SLALevelPolicy[] = [
  { level: 0, targetRole: "reviewer", deadlineMinutes: 60, autoEscalate: true },
  { level: 1, targetRole: "team_lead", deadlineMinutes: 120, autoEscalate: true },
  { level: 2, targetRole: "director", deadlineMinutes: 240, autoEscalate: true },
  { level: 3, targetRole: "c_suite", deadlineMinutes: 0, autoEscalate: false }, // No limit at L3
];

// ═══════════════════════════════════════════════════════════════════════════
// SLA Service (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class SLAService {
  private static instance: SLAService | null = null;
  private slaPolicies: SLALevelPolicy[];

  private constructor(slaPolicies?: SLALevelPolicy[]) {
    this.slaPolicies = slaPolicies ?? DEFAULT_SLA_POLICIES;
  }

  static getInstance(): SLAService {
    if (!SLAService.instance) {
      SLAService.instance = new SLAService();
    }
    return SLAService.instance;
  }

  /** Create an SLA record for an approval request */
  async createSLA(
    requestId: string,
    initialLevel?: number,
  ): Promise<EscalationSLA> {
    // Validate the request exists
    const request = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!request) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    const level = initialLevel ?? request.escalationLevel ?? 0;
    const policy = this.slaPolicies.find((p) => p.level === level);

    if (!policy) {
      throw new Error(`No SLA policy defined for level ${level}`);
    }

    const slaId = generateSLAId();
    const slaDeadline = policy.deadlineMinutes > 0
      ? new Date(Date.now() + policy.deadlineMinutes * 60 * 1000)
      : new Date(Date.now() + 365 * 24 * 60 * 60 * 1000); // 1 year for unlimited

    const record = await db.hitlEscalationSLA.create({
      data: {
        slaId,
        requestId,
        currentLevel: level,
        targetRole: policy.targetRole,
        slaDeadline,
        breached: false,
        autoEscalated: false,
        escalationReason: "",
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: "created" as HitlEventType,
      actorId: "system",
      actorName: "System",
      details: {
        action: "sla_created",
        slaId,
        currentLevel: level,
        targetRole: policy.targetRole,
        slaDeadline: slaDeadline.toISOString(),
        deadlineMinutes: policy.deadlineMinutes,
      },
    });

    return this.mapRecordToModel(record);
  }

  /** Check for SLA breaches and return breached SLA records */
  async checkSLABreaches(): Promise<EscalationSLA[]> {
    const now = new Date();

    // Find SLA records that are not yet breached and have passed their deadline
    const breached = await db.hitlEscalationSLA.findMany({
      where: {
        breached: false,
        slaDeadline: { lte: now },
      },
    });

    const result: EscalationSLA[] = [];

    for (const record of breached) {
      // Mark as breached
      const updated = await db.hitlEscalationSLA.update({
        where: { slaId: record.slaId },
        data: { breached: true },
      });

      // Record audit event
      await recordAuditEvent({
        requestId: record.requestId,
        eventType: "escalated" as HitlEventType,
        actorId: "system",
        actorName: "System",
        details: {
          action: "sla_breached",
          slaId: record.slaId,
          currentLevel: record.currentLevel,
          targetRole: record.targetRole,
          slaDeadline: record.slaDeadline.toISOString(),
        },
      });

      // Notify about the breach
      const request = await db.hitlApprovalRequest.findUnique({
        where: { requestId: record.requestId },
      });

      if (request) {
        await notifyApprovalEvent("approval_escalated", {
          requestId: record.requestId,
          title: request.title,
          priority: request.priority,
          fromLevel: record.currentLevel,
          toLevel: record.currentLevel,
          toRole: record.targetRole,
          reason: "SLA deadline breached",
          autoEscalated: false,
          slaBreached: true,
          requesterId: request.requesterId,
        });
      }

      result.push(this.mapRecordToModel(updated));
    }

    return result;
  }

  /** Auto-escalate all breached SLA records that have autoEscalate enabled */
  async autoEscalateBreached(): Promise<EscalationSLA[]> {
    const now = new Date();

    // Find breached SLAs that haven't been auto-escalated yet
    const breached = await db.hitlEscalationSLA.findMany({
      where: {
        breached: true,
        autoEscalated: false,
      },
    });

    const escalated: EscalationSLA[] = [];

    for (const record of breached) {
      const policy = this.slaPolicies.find((p) => p.level === record.currentLevel);

      if (!policy || !policy.autoEscalate) continue;

      // Check if there's a next level to escalate to
      const nextLevel = record.currentLevel + 1;
      const nextPolicy = this.slaPolicies.find((p) => p.level === nextLevel);

      if (!nextPolicy) continue;

      try {
        // Use the EscalationService for actual escalation
        const escalationService = getEscalationService();
        await escalationService.escalateRequest(record.requestId, {
          fromUserId: undefined,
          toRole: nextPolicy.targetRole,
          reason: `Auto-escalated: SLA breached at level ${record.currentLevel} (${policy.targetRole})`,
        });

        // Update the SLA record
        const slaDeadline = nextPolicy.deadlineMinutes > 0
          ? new Date(Date.now() + nextPolicy.deadlineMinutes * 60 * 1000)
          : new Date(Date.now() + 365 * 24 * 60 * 60 * 1000);

        const updated = await db.hitlEscalationSLA.update({
          where: { slaId: record.slaId },
          data: {
            autoEscalated: true,
            escalatedAt: new Date(),
            escalationReason: `Auto-escalated from level ${record.currentLevel} to ${nextLevel} due to SLA breach`,
            currentLevel: nextLevel,
            targetRole: nextPolicy.targetRole,
            slaDeadline,
            breached: false,
          },
        });

        escalated.push(this.mapRecordToModel(updated));
      } catch (error) {
        // Escalation failed (e.g., max level reached) — mark as escalated but log error
        await db.hitlEscalationSLA.update({
          where: { slaId: record.slaId },
          data: {
            autoEscalated: true,
            escalatedAt: new Date(),
            escalationReason: `Auto-escalation attempted but failed: ${
              error instanceof Error ? error.message : "Unknown error"
            }`,
          },
        });
      }
    }

    return escalated;
  }

  /** Manually escalate a request to a specific level */
  async manualEscalate(
    requestId: string,
    toLevel: number,
    reason: string,
    escalatedBy: string,
  ): Promise<EscalationSLA> {
    const request = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!request) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (request.status !== ApprovalRequestStatus.PENDING &&
        request.status !== ApprovalRequestStatus.ESCALATED) {
      throw new Error(`Cannot escalate request in status "${request.status}"`);
    }

    const targetPolicy = this.slaPolicies.find((p) => p.level === toLevel);
    if (!targetPolicy) {
      throw new Error(`No SLA policy defined for level ${toLevel}`);
    }

    // Use the EscalationService for actual escalation
    const escalationService = getEscalationService();
    await escalationService.escalateRequest(requestId, {
      fromUserId: escalatedBy,
      toRole: targetPolicy.targetRole,
      reason,
    });

    // Update or create the SLA record
    const existingSLA = await db.hitlEscalationSLA.findFirst({
      where: { requestId },
      orderBy: { createdAt: "desc" },
    });

    const slaDeadline = targetPolicy.deadlineMinutes > 0
      ? new Date(Date.now() + targetPolicy.deadlineMinutes * 60 * 1000)
      : new Date(Date.now() + 365 * 24 * 60 * 60 * 1000);

    if (existingSLA) {
      const updated = await db.hitlEscalationSLA.update({
        where: { slaId: existingSLA.slaId },
        data: {
          currentLevel: toLevel,
          targetRole: targetPolicy.targetRole,
          slaDeadline,
          breached: false,
          autoEscalated: false,
          escalatedAt: new Date(),
          escalationReason: reason,
        },
      });

      return this.mapRecordToModel(updated);
    }

    // Create a new SLA record if none exists
    const slaId = generateSLAId();
    const record = await db.hitlEscalationSLA.create({
      data: {
        slaId,
        requestId,
        currentLevel: toLevel,
        targetRole: targetPolicy.targetRole,
        slaDeadline,
        breached: false,
        autoEscalated: false,
        escalatedAt: new Date(),
        escalationReason: reason,
      },
    });

    return this.mapRecordToModel(record);
  }

  /** Get the SLA record for a request */
  async getSLARecord(requestId: string): Promise<EscalationSLA | null> {
    const record = await db.hitlEscalationSLA.findFirst({
      where: { requestId },
      orderBy: { createdAt: "desc" },
    });

    if (!record) return null;
    return this.mapRecordToModel(record);
  }

  /** Get the full escalation SLA history for a request */
  async getEscalationHistory(requestId: string): Promise<EscalationSLA[]> {
    const records = await db.hitlEscalationSLA.findMany({
      where: { requestId },
      orderBy: { createdAt: "asc" },
    });

    return records.map((r) => this.mapRecordToModel(r));
  }

  /** Map a database record to the domain model */
  private mapRecordToModel(record: {
    id: string;
    slaId: string;
    requestId: string;
    currentLevel: number;
    targetRole: string;
    slaDeadline: Date;
    breached: boolean;
    autoEscalated: boolean;
    escalatedAt: Date | null;
    escalationReason: string;
    createdAt: Date;
    updatedAt: Date;
  }): EscalationSLA {
    return {
      slaId: record.slaId,
      requestId: record.requestId,
      currentLevel: record.currentLevel,
      targetRole: record.targetRole,
      slaDeadline: record.slaDeadline.toISOString(),
      breached: record.breached,
      autoEscalated: record.autoEscalated,
      escalatedAt: record.escalatedAt?.toISOString() ?? null,
      escalationReason: record.escalationReason,
      createdAt: record.createdAt.toISOString(),
      updatedAt: record.updatedAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let slaServiceInstance: SLAService | null = null;

export function getSLAService(): SLAService {
  if (!slaServiceInstance) {
    slaServiceInstance = SLAService.getInstance();
  }
  return slaServiceInstance;
}

export function resetSLAService(): void {
  slaServiceInstance = null;
}
