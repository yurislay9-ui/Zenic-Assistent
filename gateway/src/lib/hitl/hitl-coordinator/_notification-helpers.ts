// ─── HITL Coordinator Notification Helpers ─────────────────────────────
// Extracted notification + audit + log patterns from hitl-coordinator.ts.

import {
  type ApprovalRequest,
  HitlEventType,
} from "../types";
import { getApprovalEngine } from "../approval-engine";
import { getNotificationLogService } from "../notification-log-service";
import { notifyApprovalEvent } from "../notifications";
import { recordAuditEvent } from "../approval-audit";

/** Record an audit event for a coordinator action */
export async function recordCoordinatorAudit(
  requestId: string,
  eventType: HitlEventType,
  actorId: string,
  actorName: string,
  details: Record<string, unknown>,
): Promise<void> {
  await recordAuditEvent({
    requestId,
    eventType,
    actorId,
    actorName,
    details,
  });
}

/** Send in-app notification + log it */
export async function notifyAndLog(
  request: ApprovalRequest,
  event: string,
  title: string,
  body: string,
  metadata: Record<string, unknown> = {},
): Promise<void> {
  // Send the real-time event
  try {
    await notifyApprovalEvent(event, {
      requestId: request.requestId,
      title: request.title,
      priority: request.priority,
      requesterId: request.requesterId,
      ...metadata,
    });
  } catch {
    // Notification is non-critical
  }

  // Log the notification
  try {
    const notificationLogService = getNotificationLogService();
    await notificationLogService.logNotification({
      requestId: request.requestId,
      recipientId: request.requesterId,
      channel: "in_app",
      event,
      title,
      body,
      priority: request.priority,
      metadata,
    });
  } catch {
    // Notification logging is non-critical
  }
}

/** Get a request or throw */
export async function getRequestOrThrow(requestId: string): Promise<ApprovalRequest> {
  const engine = getApprovalEngine();
  const request = await engine.getRequest(requestId);
  if (!request) {
    throw new Error(`Approval request "${requestId}" not found`);
  }
  return request;
}
