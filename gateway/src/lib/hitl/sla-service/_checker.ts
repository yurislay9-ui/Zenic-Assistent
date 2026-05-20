// ─── Zenic-Agents v3 — HITL SLA Checker Logic ───────────────────────
// SLA breach checking and auto-escalation functions.
// Extracted from sla-service.ts for modularity.

import { db } from "@/lib/db";
import {
  type EscalationSLA,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";
import { getEscalationService } from "../delegation";
import { mapSLARecordToModel } from "./_monitor";

// ═══════════════════════════════════════════════════════════════════════════
// SLA Breach Checking
// ═══════════════════════════════════════════════════════════════════════════

/** Check for SLA breaches and return breached SLA records */
export async function checkSLABreaches(
  slaPolicies: SLALevelPolicy[],
): Promise<EscalationSLA[]> {
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

    result.push(mapSLARecordToModel(updated));
  }

  return result;
}

// ═══════════════════════════════════════════════════════════════════════════
// Auto-Escalation
// ═══════════════════════════════════════════════════════════════════════════

/** Auto-escalate all breached SLA records that have autoEscalate enabled */
export async function autoEscalateBreached(
  slaPolicies: SLALevelPolicy[],
): Promise<EscalationSLA[]> {
  // Find breached SLAs that haven't been auto-escalated yet
  const breached = await db.hitlEscalationSLA.findMany({
    where: {
      breached: true,
      autoEscalated: false,
    },
  });

  const escalated: EscalationSLA[] = [];

  for (const record of breached) {
    const policy = slaPolicies.find((p) => p.level === record.currentLevel);

    if (!policy || !policy.autoEscalate) continue;

    // Check if there's a next level to escalate to
    const nextLevel = record.currentLevel + 1;
    const nextPolicy = slaPolicies.find((p) => p.level === nextLevel);

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

      escalated.push(mapSLARecordToModel(updated));
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

// ═══════════════════════════════════════════════════════════════════════════
// Shared Types
// ═══════════════════════════════════════════════════════════════════════════

export interface SLALevelPolicy {
  /** Escalation level (0-3) */
  level: number;
  /** Target role for this level */
  targetRole: string;
  /** SLA deadline in minutes */
  deadlineMinutes: number;
  /** Whether to auto-escalate on breach */
  autoEscalate: boolean;
}
