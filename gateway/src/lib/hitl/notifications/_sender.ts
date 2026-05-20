// ─── Zenic-Agents v3 — HITL Notification Service ──────────────────────
// Phase 5: In-app notifications, priority routing, digest mode
//
// FIX vs original:
//   - CRÍTICO: Eliminado almacén en memoria (Map) que crecía sin límite
//     y se perdía en restart/HMR. Ahora toda persistencia va a SQLite via Prisma.
//   - FIX #5: Singleton reset ahora limpia BOTH module var + static instance.
//   - MEDIUM: digestQueue ahora tiene max 100 por usuario (INVARIANT 3).
//   - Invariante respetada: 500MB RAM — ya no acumula notificaciones en memoria.

import { db } from "@/lib/db";
import {
  type HitlNotification,
  type NotificationChannel,
  type NotificationPriority,
  type NotificationSubscription,
  NotificationChannel as NotificationChannelEnum,
  NotificationPriority as NotificationPriorityEnum,
} from "../types";
import {
  formatNotification,
  mapPriority,
  mapEventType,
  resolveTargetUsers,
  priorityLevel,
} from "./_templates";

/** Maximum notifications per user in digest queue (INVARIANT 3) */
const MAX_DIGEST_QUEUE_SIZE = 100;

// ═══════════════════════════════════════════════════════════════════════════
// Notification Service
// ═══════════════════════════════════════════════════════════════════════════

class NotificationService {
  private static instance: NotificationService | null = null;
  private subscriptions: Map<string, NotificationSubscription> = new Map();
  private digestQueue: Map<string, string[]> = new Map(); // userId → notification IDs

  private constructor() {}

  static getInstance(): NotificationService {
    if (!NotificationService.instance) {
      NotificationService.instance = new NotificationService();
    }
    return NotificationService.instance;
  }

  /** Send a notification for an approval event */
  async notify(
    event: string,
    payload: {
      requestId: string;
      title: string;
      priority?: string;
      requesterId?: string;
      requesterName?: string;
      approverName?: string;
      rejecterName?: string;
      fromUserName?: string;
      toUserId?: string;
      toUserName?: string;
      undoByName?: string;
      undoDeadline?: string;
      reason?: string;
      fullyApproved?: boolean;
      currentApprovals?: number;
      requiredApprovals?: number;
      fromLevel?: number;
      toLevel?: number;
      toRole?: string;
      autoEscalated?: boolean;
      autoApproved?: boolean;
    },
  ): Promise<void> {
    const notificationPriority = mapPriority(payload.priority);
    const targetUserIds = resolveTargetUsers(event, payload as unknown as Record<string, unknown>);

    for (const userId of targetUserIds) {
      const subscription = this.subscriptions.get(userId);
      const channels = subscription?.channels ?? [NotificationChannelEnum.IN_APP];
      const minPriority = subscription?.minPriority ?? NotificationPriorityEnum.LOW;

      // Check priority filter
      if (priorityLevel(notificationPriority) < priorityLevel(minPriority)) continue;

      for (const channel of channels) {
        const { title: eventTitle, message } = formatNotification(event, payload as unknown as Record<string, unknown>);

        if (subscription?.digestMode && channel === NotificationChannelEnum.IN_APP) {
          // Queue for digest — store ID only, not full object
          const queue = this.digestQueue.get(userId) ?? [];

          // INVARIANT 3: cap digest queue
          if (queue.length < MAX_DIGEST_QUEUE_SIZE) {
            // Persist notification to DB immediately (even in digest mode)
            await db.hitlNotification.create({
              data: {
                userId,
                type: mapEventType(event),
                title: eventTitle,
                message,
                requestId: payload.requestId,
                priority: notificationPriority,
                channel,
                isRead: false,
              },
            });

            queue.push(payload.requestId);
            this.digestQueue.set(userId, queue);
          }
        } else {
          // Send immediately — persist to DB
          await db.hitlNotification.create({
            data: {
              userId,
              type: mapEventType(event),
              title: eventTitle,
              message,
              requestId: payload.requestId,
              priority: notificationPriority,
              channel,
              isRead: false,
            },
          });

          // Dispatch stubs for non-in-app channels
          if (channel === "email") {
            console.log(`[HITL Email Stub] To: ${userId}, Subject: ${eventTitle}`);
          } else if (channel === "webhook") {
            console.log(`[HITL Webhook Stub] Event: ${event}, Request: ${payload.requestId}`);
          }
        }
      }
    }
  }

  /** Get notifications for a user — from DB with limit */
  async getNotifications(userId: string, options?: {
    unreadOnly?: boolean;
    limit?: number;
  }): Promise<HitlNotification[]> {
    const limit = Math.min(options?.limit ?? 50, 200); // INVARIANT 3: max 200

    const where: Record<string, unknown> = { userId };
    if (options?.unreadOnly) where.isRead = false; // FIX #1 CRÍTICO: mostrar NO leídas cuando unreadOnly=true

    const records = await db.hitlNotification.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: limit,
    });

    return records.map((r) => ({
      id: r.id,
      userId: r.userId,
      type: r.type as HitlNotification["type"],
      title: r.title,
      message: r.message,
      requestId: r.requestId,
      priority: r.priority as NotificationPriority,
      channel: r.channel as NotificationChannel,
      isRead: r.isRead,
      createdAt: r.createdAt.toISOString(),
    }));
  }

  /** Mark a notification as read */
  async markAsRead(userId: string, notificationId: string): Promise<boolean> {
    const record = await db.hitlNotification.findFirst({
      where: { id: notificationId, userId },
    });

    if (!record) return false;

    await db.hitlNotification.update({
      where: { id: notificationId },
      data: { isRead: true },
    });

    return true;
  }

  /** Mark all notifications as read for a user */
  async markAllAsRead(userId: string): Promise<number> {
    const result = await db.hitlNotification.updateMany({
      where: { userId, isRead: false },
      data: { isRead: true },
    });

    return result.count;
  }

  /** Get unread count for a user */
  async getUnreadCount(userId: string): Promise<number> {
    return db.hitlNotification.count({
      where: { userId, isRead: false },
    });
  }

  /** Subscribe a user to notification channels */
  subscribe(userId: string, subscription: Partial<NotificationSubscription>): void {
    const existing = this.subscriptions.get(userId);
    this.subscriptions.set(userId, {
      userId,
      channels: subscription.channels ?? existing?.channels ?? [NotificationChannelEnum.IN_APP],
      digestMode: subscription.digestMode ?? existing?.digestMode ?? false,
      digestIntervalMinutes: subscription.digestIntervalMinutes ?? existing?.digestIntervalMinutes ?? 60,
      minPriority: subscription.minPriority ?? existing?.minPriority ?? NotificationPriorityEnum.LOW,
    });
  }

  /** Flush digest queue for a user (send batched notifications) */
  async flushDigest(userId: string): Promise<number> {
    const queue = this.digestQueue.get(userId);
    if (!queue || queue.length === 0) return 0;

    const count = queue.length;

    // Create a single digest notification
    await db.hitlNotification.create({
      data: {
        userId,
        type: "approval_pending",
        title: `${count} pending approval notifications`,
        message: `You have ${count} approval-related notifications in your digest queue.`,
        requestId: "digest",
        priority: NotificationPriorityEnum.NORMAL,
        channel: NotificationChannelEnum.IN_APP,
        isRead: false,
      },
    });

    // Clear the queue
    this.digestQueue.delete(userId);

    return count;
  }
}

// ─── Singleton Accessors — FIX #5: reset limpia AMBAS instancias ──────

let notificationServiceInstance: NotificationService | null = null;

export function getNotificationService(): NotificationService {
  if (!notificationServiceInstance) {
    notificationServiceInstance = NotificationService.getInstance();
  }
  return notificationServiceInstance;
}

export function resetNotificationService(): void {
  notificationServiceInstance = null;
  NotificationService.instance = null; // FIX: también limpia static instance
}

/** Convenience function for notifying approval events */
export async function notifyApprovalEvent(
  event: string,
  payload: Record<string, unknown>,
): Promise<void> {
  const service = getNotificationService();
  await service.notify(event, payload as Parameters<typeof service.notify>[1]);
}
