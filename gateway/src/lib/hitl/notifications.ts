// ─── Zenic-Agents v3 — HITL Notification System ──────────────────────
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
  ApprovalPriority,
} from "./types";

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
    const priority = this.mapPriority(payload.priority);
    const targetUserIds = this.resolveTargetUsers(event, payload);

    for (const userId of targetUserIds) {
      const subscription = this.subscriptions.get(userId);
      const channels = subscription?.channels ?? [NotificationChannelEnum.IN_APP];
      const minPriority = subscription?.minPriority ?? NotificationPriorityEnum.LOW;

      // Check priority filter
      if (this.priorityLevel(priority) < this.priorityLevel(minPriority)) continue;

      for (const channel of channels) {
        const { title: eventTitle, message } = this.formatNotification(event, payload);

        if (subscription?.digestMode && channel === NotificationChannelEnum.IN_APP) {
          // Queue for digest — store ID only, not full object
          const queue = this.digestQueue.get(userId) ?? [];

          // INVARIANT 3: cap digest queue
          if (queue.length < MAX_DIGEST_QUEUE_SIZE) {
            // Persist notification to DB immediately (even in digest mode)
            await db.hitlNotification.create({
              data: {
                userId,
                type: this.mapEventType(event),
                title: eventTitle,
                message,
                requestId: payload.requestId,
                priority,
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
              type: this.mapEventType(event),
              title: eventTitle,
              message,
              requestId: payload.requestId,
              priority,
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

  // ─── Private Helpers ────────────────────────────────────────────────

  private formatNotification(
    event: string,
    payload: Record<string, unknown>,
  ): { title: string; message: string } {
    const title = payload.title as string ?? "Approval Request";
    const requesterName = (payload.requesterName as string) ?? "Someone";

    switch (event) {
      case "approval_pending":
        return {
          title: `Approval Required: ${title}`,
          message: `${requesterName} requested approval for "${title}". Your review is needed.`,
        };
      case "approval_approved": {
        const approverName = (payload.approverName as string) ?? "An approver";
        const fully = payload.fullyApproved as boolean;
        return {
          title: fully ? `Approved: ${title}` : `Partially Approved: ${title}`,
          message: fully
            ? `"${title}" has been fully approved by ${approverName}.`
            : `"${title}" has been approved by ${approverName}. More approvals may be needed.`,
        };
      }
      case "approval_rejected": {
        const rejecterName = (payload.rejecterName as string) ?? "A reviewer";
        const reason = payload.reason as string;
        return {
          title: `Rejected: ${title}`,
          message: `"${title}" was rejected by ${rejecterName}.${reason ? ` Reason: ${reason}` : ""}`,
        };
      }
      case "approval_delegated": {
        const fromName = (payload.fromUserName as string) ?? "Someone";
        const toName = (payload.toUserName as string) ?? "you";
        return {
          title: `Delegated: ${title}`,
          message: `${fromName} delegated approval of "${title}" to ${toName}.`,
        };
      }
      case "approval_escalated": {
        const toLevel = payload.toLevel as number;
        const toRole = (payload.toRole as string) ?? "higher authority";
        const auto = payload.autoEscalated as boolean;
        return {
          title: `Escalated: ${title}`,
          message: auto
            ? `"${title}" was auto-escalated to level ${toLevel} (${toRole}) due to timeout.`
            : `"${title}" has been escalated to level ${toLevel} (${toRole}).`,
        };
      }
      case "approval_expired":
        return {
          title: `Expired: ${title}`,
          message: `"${title}" has expired without a decision.`,
        };
      case "approval_undone": {
        const undoByName = (payload.undoByName as string) ?? "Someone";
        const reason = payload.reason as string;
        return {
          title: `Undone: ${title}`,
          message: `${undoByName} undid the approved action for "${title}".${reason ? ` Reason: ${reason}` : ""}`,
        };
      }
      case "undo_available": {
        const undoDeadline = payload.undoDeadline as string;
        return {
          title: `Undo Available: ${title}`,
          message: `The approved action for "${title}" can be undone${undoDeadline ? ` until ${new Date(undoDeadline).toLocaleString()}` : ""}.`,
        };
      }
      default:
        return {
          title: `HITL Event: ${event}`,
          message: `Event "${event}" occurred for request "${title}".`,
        };
    }
  }

  private mapPriority(priority?: string): NotificationPriority {
    switch (priority) {
      case ApprovalPriority.EMERGENCY:
      case ApprovalPriority.CRITICAL:
        return NotificationPriorityEnum.URGENT;
      case ApprovalPriority.HIGH:
        return NotificationPriorityEnum.HIGH;
      case ApprovalPriority.MEDIUM:
        return NotificationPriorityEnum.NORMAL;
      case ApprovalPriority.LOW:
        return NotificationPriorityEnum.LOW;
      default:
        return NotificationPriorityEnum.NORMAL;
    }
  }

  private mapEventType(event: string): HitlNotification["type"] {
    const mapping: Record<string, HitlNotification["type"]> = {
      approval_pending: "approval_pending",
      approval_approved: "approval_approved",
      approval_rejected: "approval_rejected",
      approval_delegated: "approval_delegated",
      approval_escalated: "approval_escalated",
      approval_expired: "approval_expired",
      approval_undone: "approval_undone",
      undo_available: "undo_available",
    };
    return mapping[event] ?? "approval_pending";
  }

  private resolveTargetUsers(event: string, payload: Record<string, unknown>): string[] {
    const users: string[] = [];

    switch (event) {
      case "approval_pending":
        if (payload.toUserId) users.push(payload.toUserId as string);
        break;
      case "approval_approved":
      case "approval_rejected":
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_delegated":
        if (payload.toUserId) users.push(payload.toUserId as string);
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_escalated":
        if (payload.toUserId) users.push(payload.toUserId as string);
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_expired":
      case "approval_undone":
      case "undo_available":
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
    }

    return [...new Set(users)];
  }

  private priorityLevel(priority: NotificationPriority): number {
    switch (priority) {
      case NotificationPriorityEnum.LOW: return 0;
      case NotificationPriorityEnum.NORMAL: return 1;
      case NotificationPriorityEnum.HIGH: return 2;
      case NotificationPriorityEnum.URGENT: return 3;
      default: return 1;
    }
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
  await service.notify(event, payload);
}
