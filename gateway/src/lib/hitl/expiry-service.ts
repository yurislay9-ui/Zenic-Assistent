// ─── Zenic-Agents v3 — HITL Expiry Service ───────────────────────────
// Phase 5: Expiry with auto-revert for approval requests
//
// Design Patterns:
//   - Singleton: Single service instance via getExpiryService()
//   - Strategy: Configurable notification schedules per request
//   - Observer: Records audit events, triggers notifications
//   - Integration: Uses ReversibleActionService for actual undo execution

import { db } from "@/lib/db";
import {
  type ExpiryRecord,
  ApprovalRequestStatus,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";
import { notifyApprovalEvent } from "./notifications";
import { getReversibleActionService } from "./reversible-action";

// ═══════════════════════════════════════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════════════════════════════════════

/** Default TTL for approval requests (24 hours) */
const DEFAULT_EXPIRY_TTL_MS = 24 * 60 * 60 * 1000;

/** Default notification schedule: notify at 60, 30, 10, 5 minutes before expiry */
const DEFAULT_NOTIFICATION_SCHEDULE = [60, 30, 10, 5];

// ═══════════════════════════════════════════════════════════════════════════
// Expiry Service (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class ExpiryService {
  private static instance: ExpiryService | null = null;

  private constructor() {}

  static getInstance(): ExpiryService {
    if (!ExpiryService.instance) {
      ExpiryService.instance = new ExpiryService();
    }
    return ExpiryService.instance;
  }

  /** Set an expiry record for an approval request */
  async setExpiry(
    requestId: string,
    config?: {
      /** When the request expires; defaults to now + 24h */
      expiresAt?: string;
      /** Whether auto-revert is enabled on expiry */
      autoRevertEnabled?: boolean;
      /** Compensating action for auto-revert */
      revertAction?: Record<string, unknown>;
      /** Minutes before expiry to send notifications */
      notificationSchedule?: number[];
    },
  ): Promise<ExpiryRecord> {
    // Validate the request exists
    const request = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!request) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    // Check if an expiry record already exists
    const existing = await db.hitlExpiryRecord.findUnique({
      where: { requestId },
    });

    if (existing) {
      throw new Error(`Expiry record already exists for request "${requestId}"`);
    }

    const expiresAt = config?.expiresAt
      ? new Date(config.expiresAt)
      : new Date(Date.now() + DEFAULT_EXPIRY_TTL_MS);

    const autoRevertEnabled = config?.autoRevertEnabled ?? true;
    const revertAction = config?.revertAction ?? {};
    const notificationSchedule = config?.notificationSchedule ?? DEFAULT_NOTIFICATION_SCHEDULE;

    const record = await db.hitlExpiryRecord.create({
      data: {
        requestId,
        expiresAt,
        autoRevertEnabled,
        revertAction: JSON.stringify(revertAction),
        notificationSchedule: JSON.stringify(notificationSchedule),
        notificationsSent: "[]",
        status: "active",
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: "created" as HitlEventType,
      actorId: "system",
      actorName: "System",
      details: {
        action: "expiry_set",
        expiresAt: expiresAt.toISOString(),
        autoRevertEnabled,
        notificationSchedule,
      },
    });

    return this.mapRecordToModel(record);
  }

  /** Check for expired requests and process them (auto-revert if enabled) */
  async checkExpired(): Promise<ExpiryRecord[]> {
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
            const revertResult = await this.executeRevert(record.requestId);
            const updated = await db.hitlExpiryRecord.update({
              where: { requestId: record.requestId },
              data: {
                status: revertResult.success ? "reverted" : "expired",
                revertedAt: revertResult.success ? new Date() : null,
                revertResult: JSON.stringify(revertResult.result),
              },
            });
            processed.push(this.mapRecordToModel(updated));
          } else {
            const updated = await db.hitlExpiryRecord.findUnique({
              where: { requestId: record.requestId },
            });
            if (updated) processed.push(this.mapRecordToModel(updated));
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
  async executeRevert(requestId: string): Promise<{
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

  /** Cancel an expiry record (e.g., when request is approved or manually resolved) */
  async cancelExpiry(requestId: string): Promise<boolean> {
    const record = await db.hitlExpiryRecord.findUnique({
      where: { requestId },
    });

    if (!record) return false;

    if (record.status !== "active") {
      throw new Error(`Cannot cancel expiry record in status "${record.status}"`);
    }

    await db.hitlExpiryRecord.update({
      where: { requestId },
      data: { status: "cancelled" },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: "cancelled" as HitlEventType,
      actorId: "system",
      actorName: "System",
      details: { action: "expiry_cancelled" },
    });

    return true;
  }

  /** Get the expiry record for a request */
  async getExpiryRecord(requestId: string): Promise<ExpiryRecord | null> {
    const record = await db.hitlExpiryRecord.findUnique({
      where: { requestId },
    });

    if (!record) return null;
    return this.mapRecordToModel(record);
  }

  /** Check which expiry notifications are due and return them */
  async checkNotificationsDue(): Promise<Array<{
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

  /** Map a database record to the domain model */
  private mapRecordToModel(record: {
    id: string;
    requestId: string;
    expiresAt: Date;
    autoRevertEnabled: boolean;
    revertAction: string;
    notificationSchedule: string;
    notificationsSent: string;
    status: string;
    revertedAt: Date | null;
    revertResult: string | null;
    createdAt: Date;
    updatedAt: Date;
  }): ExpiryRecord {
    return {
      requestId: record.requestId,
      expiresAt: record.expiresAt.toISOString(),
      autoRevertEnabled: record.autoRevertEnabled,
      revertAction: JSON.parse(record.revertAction),
      notificationSchedule: JSON.parse(record.notificationSchedule),
      notificationsSent: JSON.parse(record.notificationsSent),
      status: record.status as ExpiryRecord["status"],
      revertedAt: record.revertedAt?.toISOString() ?? null,
      revertResult: record.revertResult ? JSON.parse(record.revertResult) : null,
      createdAt: record.createdAt.toISOString(),
      updatedAt: record.updatedAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let expiryServiceInstance: ExpiryService | null = null;

export function getExpiryService(): ExpiryService {
  if (!expiryServiceInstance) {
    expiryServiceInstance = ExpiryService.getInstance();
  }
  return expiryServiceInstance;
}

export function resetExpiryService(): void {
  expiryServiceInstance = null;
}
