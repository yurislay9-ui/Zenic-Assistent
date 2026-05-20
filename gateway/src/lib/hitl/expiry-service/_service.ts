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
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { checkExpiredRequests, checkExpiryNotificationsDue, executeRevert } from "./_checker";

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

    return mapExpiryRecordToModel(record);
  }

  /** Check for expired requests and process them (auto-revert if enabled) */
  async checkExpired(): Promise<ExpiryRecord[]> {
    return checkExpiredRequests();
  }

  /** Execute a revert action for an expired request */
  async executeRevert(requestId: string): Promise<{
    success: boolean;
    result: Record<string, unknown>;
  }> {
    return executeRevert(requestId);
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
    return mapExpiryRecordToModel(record);
  }

  /** Check which expiry notifications are due and return them */
  async checkNotificationsDue(): Promise<Array<{
    requestId: string;
    minutesRemaining: number;
  }>> {
    return checkExpiryNotificationsDue();
  }
}

// ─── Mapper (shared with _checker) ──────────────────────────────────

/** Map a database record to the domain model */
export function mapExpiryRecordToModel(record: {
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
