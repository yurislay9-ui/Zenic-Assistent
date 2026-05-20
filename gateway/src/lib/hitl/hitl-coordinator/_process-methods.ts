// ─── HITL Coordinator Process Methods ─────────────────────────────────
// Process expired, SLA breaches, and expiry notifications.
// Extracted from hitl-coordinator.ts.

import {
  type ExpiryRecord,
  type EscalationSLA,
  HitlEventType,
} from "../types";
import { getApprovalEngine } from "../approval-engine";
import { getExpiryService } from "../expiry-service";
import { getSLAService } from "../sla-service";
import { getNotificationLogService } from "../notification-log-service";
import { notifyApprovalEvent } from "../notifications";
import { recordAuditEvent } from "../approval-audit";

/** Process expired requests: check + auto-revert */
export async function processExpired(): Promise<{
  expired: ExpiryRecord[];
  reverted: Array<{ requestId: string; success: boolean }>;
}> {
  const expiryService = getExpiryService();

  const expired = await expiryService.checkExpired();
  const reverted: Array<{ requestId: string; success: boolean }> = [];

  for (const record of expired) {
    if (record.status === "reverted") {
      reverted.push({ requestId: record.requestId, success: true });
    } else if (record.status === "expired") {
      if (record.autoRevertEnabled) {
        try {
          const result = await expiryService.executeRevert(record.requestId);
          reverted.push({ requestId: record.requestId, success: result.success });
        } catch {
          reverted.push({ requestId: record.requestId, success: false });
        }
      }
    }

    await recordAuditEvent({
      requestId: record.requestId,
      eventType: HitlEventType.EXPIRED,
      actorId: "system",
      actorName: "System",
      details: {
        action: "auto_process_expired",
        expiresAt: record.expiresAt,
        autoRevertEnabled: record.autoRevertEnabled,
        status: record.status,
      },
    });

    try {
      const request = await getApprovalEngine().getRequest(record.requestId);
      if (request) {
        await notifyApprovalEvent("approval_expired", {
          requestId: record.requestId,
          title: request.title,
          priority: request.priority,
          requesterId: request.requesterId,
        });

        const notificationLogService = getNotificationLogService();
        await notificationLogService.logNotification({
          requestId: record.requestId,
          recipientId: request.requesterId,
          channel: "in_app",
          event: "approval_expired",
          title: `Expired: ${request.title}`,
          body: `Request "${request.title}" has expired without a decision.`,
          priority: request.priority,
          metadata: { autoReverted: record.status === "reverted" },
        });
      }
    } catch {
      // Notification is non-critical
    }
  }

  return { expired, reverted };
}

/** Process SLA breaches: check + auto-escalate */
export async function processSLABreaches(): Promise<{
  breached: EscalationSLA[];
  escalated: EscalationSLA[];
}> {
  const slaService = getSLAService();

  const breached = await slaService.checkSLABreaches();
  const escalated = await slaService.autoEscalateBreached();

  for (const sla of escalated) {
    await recordAuditEvent({
      requestId: sla.requestId,
      eventType: HitlEventType.ESCALATED,
      actorId: "system",
      actorName: "System",
      details: {
        action: "auto_sla_escalation",
        slaId: sla.slaId,
        currentLevel: sla.currentLevel,
        targetRole: sla.targetRole,
        escalationReason: sla.escalationReason,
      },
    });

    try {
      const request = await getApprovalEngine().getRequest(sla.requestId);
      if (request) {
        await notifyApprovalEvent("approval_escalated", {
          requestId: sla.requestId,
          title: request.title,
          priority: request.priority,
          fromLevel: sla.currentLevel - 1,
          toLevel: sla.currentLevel,
          toRole: sla.targetRole,
          autoEscalated: true,
          requesterId: request.requesterId,
        });

        const notificationLogService = getNotificationLogService();
        await notificationLogService.logNotification({
          requestId: sla.requestId,
          recipientId: request.requesterId,
          channel: "in_app",
          event: "approval_escalated",
          title: `SLA Escalated: ${request.title}`,
          body: `Request "${request.title}" was auto-escalated to level ${sla.currentLevel} (${sla.targetRole}) due to SLA breach.`,
          priority: request.priority,
          metadata: { slaId: sla.slaId, reason: sla.escalationReason },
        });
      }
    } catch {
      // Notification is non-critical
    }
  }

  return { breached, escalated };
}

/** Process expiry warning notifications */
export async function processExpiryNotifications(): Promise<Array<{ requestId: string; minutesRemaining: number }>> {
  const expiryService = getExpiryService();

  const due = await expiryService.checkNotificationsDue();

  for (const item of due) {
    try {
      const request = await getApprovalEngine().getRequest(item.requestId);
      if (request) {
        const notificationLogService = getNotificationLogService();
        await notificationLogService.logNotification({
          requestId: item.requestId,
          recipientId: request.requesterId,
          channel: "in_app",
          event: "expiry_warning",
          title: `Expiring Soon: ${request.title}`,
          body: `Request "${request.title}" expires in ${item.minutesRemaining} minutes. Please review before it expires.`,
          priority: "high",
          metadata: { minutesRemaining: item.minutesRemaining },
        });
      }
    } catch {
      // Notification logging is non-critical
    }
  }

  return due;
}
