// ─── Zenic-Agents v3 — HITL Notification Templates & Helpers ──────────
// Formatting, mapping, and routing helpers for the notification system.
// Extracted from notifications.ts for modularity.

import {
  type HitlNotification,
  type NotificationChannel,
  type NotificationPriority,
  NotificationChannel as NotificationChannelEnum,
  NotificationPriority as NotificationPriorityEnum,
  ApprovalPriority,
} from "../types";

// ═══════════════════════════════════════════════════════════════════════════
// Notification Formatting
// ═══════════════════════════════════════════════════════════════════════════

/** Format a notification title and message for a given event */
export function formatNotification(
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

// ═══════════════════════════════════════════════════════════════════════════
// Priority & Type Mapping
// ═══════════════════════════════════════════════════════════════════════════

/** Map an approval priority to a notification priority */
export function mapPriority(priority?: string): NotificationPriority {
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

/** Map an event string to a notification type */
export function mapEventType(event: string): HitlNotification["type"] {
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

/** Resolve target users for a given event */
export function resolveTargetUsers(event: string, payload: Record<string, unknown>): string[] {
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

/** Convert a notification priority to a numeric level for comparison */
export function priorityLevel(priority: NotificationPriority): number {
  switch (priority) {
    case NotificationPriorityEnum.LOW: return 0;
    case NotificationPriorityEnum.NORMAL: return 1;
    case NotificationPriorityEnum.HIGH: return 2;
    case NotificationPriorityEnum.URGENT: return 3;
    default: return 1;
  }
}
