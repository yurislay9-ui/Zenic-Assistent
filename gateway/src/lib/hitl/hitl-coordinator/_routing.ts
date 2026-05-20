// ─── Zenic-Agents v3 — HITL Coordinator (Routing / Background) ────────
// Phase 5: Background processing — undo, expiry, SLA, notifications
//
// Contains: fullUndo, processExpired, processSLABreaches,
//           processExpiryNotifications

import {
  type ExpiryRecord,
  type EscalationSLA,
  type UndoRequestInput,
  type UndoAction,
  HitlEventType,
} from "../types";
import { getApprovalEngine } from "../approval-engine";
import { getExpiryService } from "../expiry-service";
import { getSLAService } from "../sla-service";
import { getReversibleActionService } from "../reversible-action";
import { notifyApprovalEvent } from "../notifications";
import { getNotificationLogService } from "../notification-log-service";
import { recordAuditEvent } from "../approval-audit";
import { HITLCoordinator, getHITLCoordinator } from "./_coordinator";
import type {
  FullUndoResult,
  ProcessExpiredResult,
  ProcessSLABreachesResult,
  ExpiryNotificationItem,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// HITL Processing Service (Background / Routing Operations)
// ═══════════════════════════════════════════════════════════════════════════

class HITLProcessingService {
  private static instance: HITLProcessingService | null = null;

  private constructor() {}

  static getInstance(): HITLProcessingService {
    if (!HITLProcessingService.instance) {
      HITLProcessingService.instance = new HITLProcessingService();
    }
    return HITLProcessingService.instance;
  }

  /** Full undo flow: undo → record → notify */
  async fullUndo(requestId: string, undoInput: UndoRequestInput): Promise<FullUndoResult> {
    const reversibleService = getReversibleActionService();
    const expiryService = getExpiryService();

    // 1. Undo via ReversibleActionService
    const undoAction = await reversibleService.undoAction(requestId, undoInput);

    // 2. Cancel expiry
    let expiryCancelled = false;
    try {
      expiryCancelled = await expiryService.cancelExpiry(requestId);
    } catch {
      // Expiry record may not exist
    }

    // 3. Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.UNDONE,
      actorId: undoInput.undoBy,
      actorName: undoInput.undoByName,
      details: {
        action: "full_undo",
        undoType: undoInput.undoType ?? "full_undo",
        reason: undoInput.reason,
        expiryCancelled,
      },
    });

    // 4. Notify
    await notifyApprovalEvent("approval_undone", {
      requestId,
      undoByName: undoInput.undoByName,
      reason: undoInput.reason,
    });

    // 5. Log notification
    try {
      const request = await getApprovalEngine().getRequest(requestId);
      if (request) {
        const notificationLogService = getNotificationLogService();
        await notificationLogService.logNotification({
          requestId,
          recipientId: request.requesterId,
          channel: "in_app",
          event: "approval_undone",
          title: `Undone: ${request.title}`,
          body: `${undoInput.undoByName} undid the action. Reason: ${undoInput.reason}`,
          priority: request.priority,
          metadata: { undoType: undoInput.undoType ?? "full_undo" },
        });
      }
    } catch {
      // Notification logging is non-critical
    }

    return { undoAction, expiryCancelled };
  }

  /** Process expired requests: check + auto-revert */
  async processExpired(): Promise<ProcessExpiredResult> {
    const expiryService = getExpiryService();

    // 1. Check for expired requests
    const expired = await expiryService.checkExpired();

    // 2. Track reverts
    const reverted: Array<{ requestId: string; success: boolean }> = [];

    for (const record of expired) {
      if (record.status === "reverted") {
        reverted.push({ requestId: record.requestId, success: true });
      } else if (record.status === "expired") {
        // Attempt to revert if auto-revert is enabled
        if (record.autoRevertEnabled) {
          try {
            const result = await expiryService.executeRevert(record.requestId);
            reverted.push({ requestId: record.requestId, success: result.success });
          } catch {
            reverted.push({ requestId: record.requestId, success: false });
          }
        }
      }

      // 3. Record audit event
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

      // 4. Notify
      try {
        const request = await getApprovalEngine().getRequest(record.requestId);
        if (request) {
          await notifyApprovalEvent("approval_expired", {
            requestId: record.requestId,
            title: request.title,
            priority: request.priority,
            requesterId: request.requesterId,
          });

          // Log notification
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
  async processSLABreaches(): Promise<ProcessSLABreachesResult> {
    const slaService = getSLAService();

    // 1. Check for SLA breaches
    const breached = await slaService.checkSLABreaches();

    // 2. Auto-escalate breached requests
    const escalated = await slaService.autoEscalateBreached();

    // 3. Record audit events for each escalation
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

      // 4. Notify
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

          // Log notification
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
  async processExpiryNotifications(): Promise<ExpiryNotificationItem[]> {
    const expiryService = getExpiryService();

    // 1. Check notifications due via ExpiryService
    const due = await expiryService.checkNotificationsDue();

    // 2. Send warning notifications & log them
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
}

// ─── Singleton Accessor ───────────────────────────────────────────────

let processingServiceInstance: HITLProcessingService | null = null;

export function getHITLProcessingService(): HITLProcessingService {
  if (!processingServiceInstance) {
    processingServiceInstance = HITLProcessingService.getInstance();
  }
  return processingServiceInstance;
}

export function resetHITLProcessingService(): void {
  processingServiceInstance = null;
}

// Re-export coordinator singletons for backward compatibility
export { HITLCoordinator, getHITLCoordinator, resetHITLCoordinator } from "./_coordinator";
