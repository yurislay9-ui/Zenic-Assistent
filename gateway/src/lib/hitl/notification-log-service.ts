// ─── Zenic-Agents v3 — HITL Notification Log Service ──────────────────
// Phase 5: Persistent notification dispatch logs
//
// Design Patterns:
//   - Singleton: Single service instance via getNotificationLogService()
//   - Observer: Logs every notification dispatched
//   - Repository: Prisma-backed persistence for notification logs

import { db } from "@/lib/db";
import {
  type NotificationLogRecord,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// ID Generation
// ═══════════════════════════════════════════════════════════════════════════

function generateNotificationId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `ntf_${timestamp}_${random}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Log Notification Input
// ═══════════════════════════════════════════════════════════════════════════

export interface LogNotificationInput {
  /** Request ID this notification relates to */
  requestId: string;
  /** Recipient user ID */
  recipientId: string;
  /** Channel: in_app, email, slack, teams, whatsapp, sms, push, webhook */
  channel: string;
  /** Event type */
  event: string;
  /** Notification title */
  title: string;
  /** Notification body */
  body: string;
  /** Priority: low, normal, high, urgent */
  priority?: string;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Notification Log Service (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class NotificationLogService {
  private static instance: NotificationLogService | null = null;

  private constructor() {}

  static getInstance(): NotificationLogService {
    if (!NotificationLogService.instance) {
      NotificationLogService.instance = new NotificationLogService();
    }
    return NotificationLogService.instance;
  }

  /** Log a notification dispatch */
  async logNotification(input: LogNotificationInput): Promise<NotificationLogRecord> {
    const notificationId = generateNotificationId();

    const record = await db.hitlNotificationLog.create({
      data: {
        notificationId,
        requestId: input.requestId,
        recipientId: input.recipientId,
        channel: input.channel,
        event: input.event,
        title: input.title,
        body: input.body,
        priority: input.priority ?? "normal",
        status: "pending",
        metadata: JSON.stringify(input.metadata ?? {}),
      },
    });

    return this.mapRecordToModel(record);
  }

  /** Get notification history for a request
   *  FIX #7: Añadido take con límite.
   */
  async getNotificationHistory(requestId: string, limit = 100): Promise<NotificationLogRecord[]> {
    const records = await db.hitlNotificationLog.findMany({
      where: { requestId },
      orderBy: { createdAt: "desc" },
      take: Math.min(limit, 200), // INVARIANT 3
    });

    return records.map((r) => this.mapRecordToModel(r));
  }

  /** Get notification history for a specific user */
  async getNotificationHistoryForUser(
    userId: string,
    options?: {
      channel?: string;
      event?: string;
      status?: string;
      limit?: number;
    },
  ): Promise<NotificationLogRecord[]> {
    const where: Record<string, unknown> = { recipientId: userId };

    if (options?.channel) where.channel = options.channel;
    if (options?.event) where.event = options.event;
    if (options?.status) where.status = options.status;

    const records = await db.hitlNotificationLog.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 100,
    });

    return records.map((r) => this.mapRecordToModel(r));
  }

  /** Mark a notification as sent */
  async markAsSent(notificationId: string): Promise<NotificationLogRecord> {
    const record = await db.hitlNotificationLog.findUnique({
      where: { notificationId },
    });

    if (!record) {
      throw new Error(`Notification "${notificationId}" not found`);
    }

    if (record.status !== "pending") {
      throw new Error(`Cannot mark notification in status "${record.status}" as sent`);
    }

    const updated = await db.hitlNotificationLog.update({
      where: { notificationId },
      data: {
        status: "sent",
        sentAt: new Date(),
      },
    });

    return this.mapRecordToModel(updated);
  }

  /** Mark a notification as delivered */
  async markAsDelivered(notificationId: string): Promise<NotificationLogRecord> {
    const record = await db.hitlNotificationLog.findUnique({
      where: { notificationId },
    });

    if (!record) {
      throw new Error(`Notification "${notificationId}" not found`);
    }

    if (record.status !== "sent") {
      throw new Error(`Cannot mark notification in status "${record.status}" as delivered`);
    }

    const updated = await db.hitlNotificationLog.update({
      where: { notificationId },
      data: {
        status: "delivered",
        deliveredAt: new Date(),
      },
    });

    return this.mapRecordToModel(updated);
  }

  /** Mark a notification as failed */
  async markAsFailed(notificationId: string, errorMessage: string): Promise<NotificationLogRecord> {
    const record = await db.hitlNotificationLog.findUnique({
      where: { notificationId },
    });

    if (!record) {
      throw new Error(`Notification "${notificationId}" not found`);
    }

    if (record.status !== "pending" && record.status !== "sent") {
      throw new Error(`Cannot mark notification in status "${record.status}" as failed`);
    }

    const updated = await db.hitlNotificationLog.update({
      where: { notificationId },
      data: {
        status: "failed",
        failedAt: new Date(),
        errorMessage,
      },
    });

    return this.mapRecordToModel(updated);
  }

  /** Retry a failed notification */
  async retryFailed(notificationId: string): Promise<NotificationLogRecord> {
    const record = await db.hitlNotificationLog.findUnique({
      where: { notificationId },
    });

    if (!record) {
      throw new Error(`Notification "${notificationId}" not found`);
    }

    if (record.status !== "failed") {
      throw new Error(`Cannot retry notification in status "${record.status}"`);
    }

    // Reset to pending for retry
    const updated = await db.hitlNotificationLog.update({
      where: { notificationId },
      data: {
        status: "pending",
        sentAt: null,
        deliveredAt: null,
        failedAt: null,
        errorMessage: null,
      },
    });

    return this.mapRecordToModel(updated);
  }

  /** Map a database record to the domain model */
  private mapRecordToModel(record: {
    id: string;
    notificationId: string;
    requestId: string;
    recipientId: string;
    channel: string;
    event: string;
    title: string;
    body: string;
    priority: string;
    status: string;
    metadata: string;
    sentAt: Date | null;
    deliveredAt: Date | null;
    failedAt: Date | null;
    errorMessage: string | null;
    createdAt: Date;
  }): NotificationLogRecord {
    return {
      notificationId: record.notificationId,
      requestId: record.requestId,
      recipientId: record.recipientId,
      channel: record.channel,
      event: record.event,
      title: record.title,
      body: record.body,
      priority: record.priority,
      status: record.status as NotificationLogRecord["status"],
      metadata: JSON.parse(record.metadata),
      sentAt: record.sentAt?.toISOString() ?? null,
      deliveredAt: record.deliveredAt?.toISOString() ?? null,
      failedAt: record.failedAt?.toISOString() ?? null,
      errorMessage: record.errorMessage,
      createdAt: record.createdAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let notificationLogServiceInstance: NotificationLogService | null = null;

export function getNotificationLogService(): NotificationLogService {
  if (!notificationLogServiceInstance) {
    notificationLogServiceInstance = NotificationLogService.getInstance();
  }
  return notificationLogServiceInstance;
}

export function resetNotificationLogService(): void {
  notificationLogServiceInstance = null;
}
