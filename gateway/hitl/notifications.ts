// ─── Zenic-Agents v3 — HITL Notification System ──────────────────────
// Phase 5: In-app notifications, priority routing, digest mode
//
// Design Patterns:
//   - Observer: Notification listeners for approval events
//   - Strategy: Notification channel dispatch strategies
//   - Singleton: NotificationService instance

import {
  type HitlNotification,
  type NotificationChannel,
  type NotificationPriority,
  type NotificationSubscription,
  NotificationChannel as NotificationChannelEnum,
  NotificationPriority as NotificationPriorityEnum,
  ApprovalPriority,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// In-Memory Notification Store (production would use DB + WebSocket)
// ═══════════════════════════════════════════════════════════════════════════

interface StoredNotification extends HitlNotification {
  id: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Notification Service
// ═══════════════════════════════════════════════════════════════════════════

class NotificationService {
  private static instance: NotificationService | null = null;
  private notifications: Map<string, StoredNotification[]> = new Map();
  private subscriptions: Map<string, NotificationSubscription> = new Map();
  private digestQueue: Map<string, StoredNotification[]> = new Map();

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
        const notification = this.createNotification(
          userId,
          event,
          payload,
          priority,
          channel,
        );

        if (subscription?.digestMode && channel === NotificationChannelEnum.IN_APP) {
          // Queue for digest
          const queue = this.digestQueue.get(userId) ?? [];
          queue.push(notification);
          this.digestQueue.set(userId, queue);
        } else {
          // Send immediately
          await this.dispatchNotification(notification, channel);
        }
      }
    }
  }

  /** Get notifications for a user */
  getNotifications(userId: string, options?: {
    unreadOnly?: boolean;
    limit?: number;
  }): HitlNotification[] {
    const userNotifications = this.notifications.get(userId) ?? [];
    let filtered = [...userNotifications];

    if (options?.unreadOnly) {
      filtered = filtered.filter((n) => !n.isRead);
    }

    // Sort by creation time, newest first
    filtered.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    if (options?.limit) {
      filtered = filtered.slice(0, options.limit);
    }

    return filtered;
  }

  /** Mark a notification as read */
  markAsRead(userId: string, notificationId: string): boolean {
    const userNotifications = this.notifications.get(userId);
    if (!userNotifications) return false;

    const notification = userNotifications.find((n) => n.id === notificationId);
    if (!notification) return false;

    notification.isRead = true;
    return true;
  }

  /** Mark all notifications as read for a user */
  markAllAsRead(userId: string): number {
    const userNotifications = this.notifications.get(userId);
    if (!userNotifications) return 0;

    let count = 0;
    for (const n of userNotifications) {
      if (!n.isRead) {
        n.isRead = true;
        count++;
      }
    }
    return count;
  }

  /** Get unread count for a user */
  getUnreadCount(userId: string): number {
    const userNotifications = this.notifications.get(userId) ?? [];
    return userNotifications.filter((n) => !n.isRead).length;
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
  flushDigest(userId: string): number {
    const queue = this.digestQueue.get(userId);
    if (!queue || queue.length === 0) return 0;

    // Create a single digest notification
    const count = queue.length;
    const first = queue[0];

    const digestNotification: StoredNotification = {
      id: `notif_digest_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      userId,
      type: "approval_pending",
      title: `${count} pending approval notifications`,
      message: `You have ${count} approval-related notifications. Latest: ${first.title}`,
      requestId: first.requestId,
      priority: NotificationPriorityEnum.NORMAL,
      channel: NotificationChannelEnum.IN_APP,
      isRead: false,
      createdAt: new Date().toISOString(),
    };

    const userNotifications = this.notifications.get(userId) ?? [];
    userNotifications.push(digestNotification);
    this.notifications.set(userId, userNotifications);

    // Clear the queue
    this.digestQueue.delete(userId);

    return count;
  }

  // ─── Private Helpers ────────────────────────────────────────────────

  private createNotification(
    userId: string,
    event: string,
    payload: Record<string, unknown>,
    priority: NotificationPriority,
    channel: NotificationChannel,
  ): StoredNotification {
    const id = `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const { title: eventTitle, message } = this.formatNotification(event, payload);

    return {
      id,
      userId,
      type: this.mapEventType(event),
      title: eventTitle,
      message,
      requestId: payload.requestId as string,
      priority,
      channel,
      isRead: false,
      createdAt: new Date().toISOString(),
    };
  }

  private async dispatchNotification(notification: StoredNotification, channel: NotificationChannel): Promise<void> {
    switch (channel) {
      case "in_app": {
        const userNotifications = this.notifications.get(notification.userId) ?? [];
        userNotifications.push(notification);
        this.notifications.set(notification.userId, userNotifications);
        break;
      }
      case "email":
        // Stub: In production, integrate with email service
        console.log(`[HITL Email Stub] To: ${notification.userId}, Subject: ${notification.title}`);
        break;
      case "webhook":
        // Stub: In production, POST to configured webhook URL
        console.log(`[HITL Webhook Stub] Event: ${notification.type}, Request: ${notification.requestId}`);
        break;
    }
  }

  private resolveTargetUsers(event: string, payload: Record<string, unknown>): string[] {
    const users: string[] = [];

    switch (event) {
      case "approval_pending":
        // Notify all potential approvers (in a real system, this would be role-based)
        // For now, just notify if there's a specific target
        if (payload.toUserId) users.push(payload.toUserId as string);
        break;
      case "approval_approved":
      case "approval_rejected":
        // Notify the requester
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_delegated":
        // Notify the delegate
        if (payload.toUserId) users.push(payload.toUserId as string);
        // Also notify the requester
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_escalated":
        // Notify approvers at the new level
        if (payload.toUserId) users.push(payload.toUserId as string);
        // Also notify the requester
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_expired":
        // Notify the requester
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "approval_undone":
        // Notify the requester and relevant approvers
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
      case "undo_available":
        // Notify the requester
        if (payload.requesterId) users.push(payload.requesterId as string);
        break;
    }

    return [...new Set(users)]; // Deduplicate
  }

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

// ─── Singleton Accessors ──────────────────────────────────────────────

let notificationServiceInstance: NotificationService | null = null;

export function getNotificationService(): NotificationService {
  if (!notificationServiceInstance) {
    notificationServiceInstance = NotificationService.getInstance();
  }
  return notificationServiceInstance;
}

export function resetNotificationService(): void {
  notificationServiceInstance = null;
}

/** Convenience function for notifying approval events */
export async function notifyApprovalEvent(
  event: string,
  payload: Record<string, unknown>,
): Promise<void> {
  const service = getNotificationService();
  await service.notify(event, payload);
}
