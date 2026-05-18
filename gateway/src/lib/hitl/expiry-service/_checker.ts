// ─── Zenic-Agents v3 — HITL Expiry Checker Logic ────────────────────
// Periodic checking functions for expired requests and notification schedules.
// Extracted from expiry-service.ts for modularity.

import { db } from "@/lib/db";
import {
  type ExpiryRecord,
  ApprovalRequestStatus,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";
import { getReversibleActionService } from "../reversible-action";
import { mapExpiryRecordToModel } from "./_service";

// ═══════════════════════════════════════════════════════════════════════════
// Periodic Checking Functions
// ═══════════════════════════════════════════════════════════════════════════

/** Check for expired requests and process them (auto-revert if enabled) */
export async function checkExpiredRequests(): Promise<ExpiryRecord[]> {
  const now = new Date();

  // Find all active expiry records that have passed their deadline
  const expired = await db.hitlExpiryRecord.findMany({
    where: {
      status: "active",
      expiresAt: { lte: now },
    },
  });

  const processed: ExpiryRecord[] = [];

  for (const record of expired) {
    try {
      // Mark as expired
      await db.hitlExpiryRecord.update({
        where: { requestId: record.requestId },
        data: { status: "expired" },
      });

      // Update the approval request status
      const request = await db.hitlApprovalRequest.findUnique({
        where: { requestId: record.requestId },
      });

      if (request) {
        await db.hitlApprovalRequest.update({
          where: { requestId: record.requestId },
          data: { status: ApprovalRequestStatus.EXPIRED },
        });

        // Record audit event
        await recordAuditEvent({
          requestId: record.requestId,
          eventType: HitlEventType.EXPIRED,
          actorId: "system",
          actorName: "System",
          details: {
            expiresAt: record.expiresAt.toISOString(),
            autoRevertEnabled: record.autoRevertEnabled,
          },
        });

        // Notify
        await notifyApprovalEvent("approval_expired", {
          requestId: record.requestId,
          title: request.title,
          priority: request.priority,
          requesterId: request.requesterId,
        });

        // Auto-revert if enabled
        if (record.autoRevertEnabled) {
          const revertResult = await executeRevert(record.requestId);
          const updated = await db.hitlExpiryRecord.update({
            where: { requestId: record.requestId },
            data: {
              status: revertResult.success ? "reverted" : "expired",
              revertedAt: revertResult.success ? new Date() : null,
              revertResult: JSON.stringify(revertResult.result),
            },
          });
          processed.push(mapExpiryRecordToModel(updated));
        } else {
          const updated = await db.hitlExpiryRecord.findUnique({
            where: { requestId: record.requestId },
          });
          if (updated) processed.push(mapExpiryRecordToModel(updated));
        }
      }
    } catch (error) {
      // Log error but continue processing other records
      console.error(
        `[ExpiryService] Error processing expiry for ${record.requestId}:`,
        error instanceof Error ? error.message : "Unknown error",
      );
    }
  }

  return processed;
}

/** Execute a revert action for an expired request */
export async function executeRevert(requestId: string): Promise<{
  success: boolean;
  result: Record<string, unknown>;
}> {
  const record = await db.hitlExpiryRecord.findUnique({
    where: { requestId },
  });

  if (!record) {
    throw new Error(`Expiry record for request "${requestId}" not found`);
  }

  const request = await db.hitlApprovalRequest.findUnique({
    where: { requestId },
  });

  if (!request) {
    throw new Error(`Approval request "${requestId}" not found`);
  }

  const revertAction = JSON.parse(record.revertAction) as Record<string, unknown>;

  // If the request was executed and is reversible, use the ReversibleActionService
  if (request.executedAt && request.isReversible && !request.undoExecutedAt) {
    try {
      const reversibleService = getReversibleActionService();
      const undoResult = await reversibleService.undoAction(requestId, {
        undoBy: "system",
        undoByName: "System Auto-Revert",
        reason: "Auto-reverted due to approval request expiry",
        undoType: "compensating_action",
      });

      return {
        success: true,
        result: {
          autoReverted: true,
          undoResult,
        },
      };
    } catch (error) {
      return {
        success: false,
        result: {
          autoReverted: false,
          error: error instanceof Error ? error.message : "Unknown error during revert",
          revertAction,
        },
      };
    }
  }

  // If not executed yet, just mark as expired (no revert needed)
  return {
    success: true,
    result: {
      autoReverted: false,
      reason: "Action was not executed, no revert needed",
    },
  };
}

/** Check which expiry notifications are due and return them */
export async function checkExpiryNotificationsDue(): Promise<Array<{
  requestId: string;
  minutesRemaining: number;
}>> {
  const now = new Date();

  // Find all active expiry records
  const activeRecords = await db.hitlExpiryRecord.findMany({
    where: { status: "active" },
  });

  const due: Array<{ requestId: string; minutesRemaining: number }> = [];

  for (const record of activeRecords) {
    const schedule = JSON.parse(record.notificationSchedule) as number[];
    const sent = JSON.parse(record.notificationsSent) as Array<{
      minutesBefore: number;
      sentAt: string;
    }>;

    const minutesRemaining = Math.round(
      (record.expiresAt.getTime() - now.getTime()) / 60000,
    );

    // Check each schedule entry
    for (const minutesBefore of schedule) {
      const alreadySent = sent.some((s) => s.minutesBefore === minutesBefore);

      if (!alreadySent && minutesRemaining <= minutesBefore && minutesRemaining > 0) {
        due.push({
          requestId: record.requestId,
          minutesRemaining,
        });

        // Record that this notification was sent
        sent.push({ minutesBefore, sentAt: now.toISOString() });
        await db.hitlExpiryRecord.update({
          where: { requestId: record.requestId },
          data: { notificationsSent: JSON.stringify(sent) },
        });

        // Send the notification
        const request = await db.hitlApprovalRequest.findUnique({
          where: { requestId: record.requestId },
        });

        if (request) {
          await notifyApprovalEvent("approval_expired", {
            requestId: record.requestId,
            title: request.title,
            priority: request.priority,
            requesterId: request.requesterId,
            minutesRemaining,
            isWarning: true,
          });
        }

        break; // Only one notification per check per record
      }
    }
  }

  return due;
}
