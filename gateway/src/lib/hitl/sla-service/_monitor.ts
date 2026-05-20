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
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { getEscalationService } from "../delegation";
import { checkSLABreaches, autoEscalateBreached, type SLALevelPolicy } from "./_checker";

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

    return mapSLARecordToModel(record);
  }

  /** Check for SLA breaches and return breached SLA records */
  async checkSLABreaches(): Promise<EscalationSLA[]> {
    return checkSLABreaches(this.slaPolicies);
  }

  /** Auto-escalate all breached SLA records that have autoEscalate enabled */
  async autoEscalateBreached(): Promise<EscalationSLA[]> {
    return autoEscalateBreached(this.slaPolicies);
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

      return mapSLARecordToModel(updated);
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

    return mapSLARecordToModel(record);
  }

  /** Get the SLA record for a request */
  async getSLARecord(requestId: string): Promise<EscalationSLA | null> {
    const record = await db.hitlEscalationSLA.findFirst({
      where: { requestId },
      orderBy: { createdAt: "desc" },
    });

    if (!record) return null;
    return mapSLARecordToModel(record);
  }

  /** Get the full escalation SLA history for a request
   *  FIX #7: Añadido take con límite.
   */
  async getEscalationHistory(requestId: string, limit = 50): Promise<EscalationSLA[]> {
    const records = await db.hitlEscalationSLA.findMany({
      where: { requestId },
      orderBy: { createdAt: "asc" },
      take: Math.min(limit, 200), // INVARIANT 3
    });

    return records.map((r) => mapSLARecordToModel(r));
  }
}

// ─── Mapper (shared with _checker) ──────────────────────────────────

/** Map a database record to the domain model */
export function mapSLARecordToModel(record: {
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
