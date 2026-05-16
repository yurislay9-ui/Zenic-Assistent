// ─── Zenic-Agents v3 — HITL Coordinator ─────────────────────────────────
// Phase 5: Central orchestrator — Facade pattern
//
// Wires together: ApprovalEngine + EvidenceService + JustificationService +
//   ExpiryService + SLAService + DelegationService + EscalationService +
//   ReversibleActionService + NotificationLogService + ApprovalAudit
//
// Design Patterns:
//   - Facade: Single entry point for all HITL operations
//   - Coordinator: Orchestrates cross-service workflows
//   - Singleton: Single coordinator instance

import { db } from "@/lib/db";
import {
  type ApprovalRequest,
  type ApprovalEvidence,
  type ApprovalJustification,
  type ExpiryRecord,
  type EscalationSLA,
  type ApprovalAuditRecord,
  type ApprovalTimelineEvent,
  type ApprovalDecision,
  type ExtendedCreateApprovalRequestInput,
  type ApproveRequestInput,
  type RejectRequestInput,
  type ProvideJustificationInput,
  type UndoRequestInput,
  type UndoAction,
  HitlEventType,
} from "./types";
import { getApprovalEngine } from "./approval-engine";
import { getEvidenceService } from "./evidence-service";
import { getJustificationService } from "./justification-service";
import { getExpiryService } from "./expiry-service";
import { getSLAService } from "./sla-service";
import { getReversibleActionService } from "./reversible-action";
import { notifyApprovalEvent } from "./notifications";
import { getNotificationLogService } from "./notification-log-service";
import { recordAuditEvent, getAuditTrail, getApprovalTimeline } from "./approval-audit";

// ═══════════════════════════════════════════════════════════════════════════
// HITL Coordinator (Facade + Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class HITLCoordinator {
  private static instance: HITLCoordinator | null = null;

  private constructor() {}

  static getInstance(): HITLCoordinator {
    if (!HITLCoordinator.instance) {
      HITLCoordinator.instance = new HITLCoordinator();
    }
    return HITLCoordinator.instance;
  }

  // ─── Full lifecycle methods ────────────────────────────────────────

  /** Create a full approval request with evidence, justification, expiry, and SLA */
  async createFullRequest(input: ExtendedCreateApprovalRequestInput): Promise<{
    request: ApprovalRequest;
    evidence: ApprovalEvidence[];
    justification: ApprovalJustification | null;
    expiry: ExpiryRecord;
    sla: EscalationSLA;
  }> {
    const engine = getApprovalEngine();
    const evidenceService = getEvidenceService();
    const justificationService = getJustificationService();
    const expiryService = getExpiryService();
    const slaService = getSLAService();

    // 1. Create the base approval request
    const request = await engine.createRequest(input);

    // 2. Attach evidence if provided
    const evidence: ApprovalEvidence[] = [];
    if (input.evidence && input.evidence.length > 0) {
      for (const ev of input.evidence) {
        const attached = await evidenceService.attachEvidence(request.requestId, ev);
        evidence.push(attached);
      }
    }

    // 3. Create justification if provided
    let justification: ApprovalJustification | null = null;
    if (input.justification) {
      justification = await justificationService.provideJustification(
        request.requestId,
        input.justification,
      );
    }

    // 4. Set expiry with auto-revert
    const expiry = await expiryService.setExpiry(request.requestId, {
      expiresAt: input.deadline ?? undefined,
      autoRevertEnabled: input.autoRevertOnExpiry ?? true,
      revertAction: input.revertAction ?? input.undoPayload,
      notificationSchedule: input.expiryNotificationSchedule,
    });

    // 5. Create SLA record
    const sla = await slaService.createSLA(request.requestId);

    return { request, evidence, justification, expiry, sla };
  }

  /** Full approve flow: validate justification → approve → execute → notify */
  async fullApprove(
    requestId: string,
    approveInput: ApproveRequestInput,
    justificationInput: ProvideJustificationInput,
  ): Promise<{
    request: ApprovalRequest;
    justification: ApprovalJustification;
    executionResult?: { success: boolean; executionResult: Record<string, unknown>; snapshot: Record<string, unknown> };
  }> {
    const engine = getApprovalEngine();
    const justificationService = getJustificationService();
    const expiryService = getExpiryService();
    const reversibleService = getReversibleActionService();

    // 1. Get the request to check priority for justification validation
    const existingRequest = await engine.getRequest(requestId);
    if (!existingRequest) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    // 2. Validate justification requirements
    const validation = justificationService.validateJustification(
      justificationInput,
      existingRequest.priority,
    );
    if (!validation.valid) {
      throw new Error(`Justification validation failed: ${validation.errors.join("; ")}`);
    }

    // 3. Store justification
    const justification = await justificationService.provideJustification(
      requestId,
      justificationInput,
      existingRequest.priority,
    );

    // 4. Approve via ApprovalEngine
    const request = await engine.approveRequest(requestId, approveInput);

    // 5. If fully approved, execute the action
    let executionResult: { success: boolean; executionResult: Record<string, unknown>; snapshot: Record<string, unknown> } | undefined;
    if (request.status === "approved" && !request.executedAt) {
      try {
        const result = await reversibleService.executeApprovedAction(requestId);
        executionResult = result;
      } catch (error) {
        // Execution failed but approval is still recorded
        console.error(
          `[HITLCoordinator] Action execution failed for ${requestId}:`,
          error instanceof Error ? error.message : "Unknown error",
        );
      }
    }

    // 6. Cancel expiry (request resolved)
    try {
      await expiryService.cancelExpiry(requestId);
    } catch {
      // Expiry record may not exist — that's fine
    }

    // 7. Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.APPROVED,
      actorId: approveInput.decisionBy,
      actorName: approveInput.decisionByName,
      details: {
        action: "full_approve",
        justificationId: justification.justificationId,
        executed: !!executionResult,
        executionSuccess: executionResult?.success,
      },
    });

    // 8. Log notification
    try {
      const notificationLogService = getNotificationLogService();
      await notificationLogService.logNotification({
        requestId,
        recipientId: existingRequest.requesterId,
        channel: "in_app",
        event: "approval_approved",
        title: `Approved: ${existingRequest.title}`,
        body: `Request "${existingRequest.title}" has been approved by ${approveInput.decisionByName}.`,
        priority: existingRequest.priority,
        metadata: { justificationId: justification.justificationId },
      });
    } catch {
      // Notification logging is non-critical
    }

    return { request, justification, executionResult };
  }

  /** Full reject flow: validate justification → reject → notify */
  async fullReject(
    requestId: string,
    rejectInput: RejectRequestInput,
    justificationInput: ProvideJustificationInput,
  ): Promise<{
    request: ApprovalRequest;
    justification: ApprovalJustification;
  }> {
    const engine = getApprovalEngine();
    const justificationService = getJustificationService();
    const expiryService = getExpiryService();

    // 1. Get the request to check priority for justification validation
    const existingRequest = await engine.getRequest(requestId);
    if (!existingRequest) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    // 2. Validate justification requirements
    const validation = justificationService.validateJustification(
      justificationInput,
      existingRequest.priority,
    );
    if (!validation.valid) {
      throw new Error(`Justification validation failed: ${validation.errors.join("; ")}`);
    }

    // 3. Store justification
    const justification = await justificationService.provideJustification(
      requestId,
      justificationInput,
      existingRequest.priority,
    );

    // 4. Reject via ApprovalEngine
    const request = await engine.rejectRequest(requestId, rejectInput);

    // 5. Cancel expiry
    try {
      await expiryService.cancelExpiry(requestId);
    } catch {
      // Expiry record may not exist — that's fine
    }

    // 6. Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.REJECTED,
      actorId: rejectInput.decisionBy,
      actorName: rejectInput.decisionByName,
      details: {
        action: "full_reject",
        justificationId: justification.justificationId,
        reason: rejectInput.comment,
      },
    });

    // 7. Log notification
    try {
      const notificationLogService = getNotificationLogService();
      await notificationLogService.logNotification({
        requestId,
        recipientId: existingRequest.requesterId,
        channel: "in_app",
        event: "approval_rejected",
        title: `Rejected: ${existingRequest.title}`,
        body: `Request "${existingRequest.title}" was rejected by ${rejectInput.decisionByName}. Reason: ${rejectInput.comment}`,
        priority: existingRequest.priority,
        metadata: { justificationId: justification.justificationId },
      });
    } catch {
      // Notification logging is non-critical
    }

    return { request, justification };
  }

  /** Full undo flow: undo → record → notify */
  async fullUndo(requestId: string, undoInput: UndoRequestInput): Promise<{
    undoAction: UndoAction;
    expiryCancelled: boolean;
  }> {
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
  async processExpired(): Promise<{
    expired: ExpiryRecord[];
    reverted: Array<{ requestId: string; success: boolean }>;
  }> {
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
  async processSLABreaches(): Promise<{
    breached: EscalationSLA[];
    escalated: EscalationSLA[];
  }> {
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
  async processExpiryNotifications(): Promise<Array<{ requestId: string; minutesRemaining: number }>> {
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

  /** Get full request details with all related data */
  async getFullRequestDetails(requestId: string): Promise<{
    request: ApprovalRequest | null;
    evidence: ApprovalEvidence[];
    justification: ApprovalJustification | null;
    expiry: ExpiryRecord | null;
    sla: EscalationSLA | null;
    auditTrail: ApprovalAuditRecord[];
    timeline: ApprovalTimelineEvent[];
    decisions: ApprovalDecision[];
  }> {
    const engine = getApprovalEngine();
    const evidenceService = getEvidenceService();
    const justificationService = getJustificationService();
    const expiryService = getExpiryService();
    const slaService = getSLAService();

    // Fetch request first
    const request = await engine.getRequest(requestId);
    if (!request) {
      return {
        request: null,
        evidence: [],
        justification: null,
        expiry: null,
        sla: null,
        auditTrail: [],
        timeline: [],
        decisions: [],
      };
    }

    // Gather all related data in parallel
    const [evidence, justification, expiry, sla, auditTrail, timeline, decisions] = await Promise.all([
      evidenceService.getEvidence(requestId).catch(() => [] as ApprovalEvidence[]),
      justificationService.getJustification(requestId).catch(() => null as ApprovalJustification | null),
      expiryService.getExpiryRecord(requestId).catch(() => null as ExpiryRecord | null),
      slaService.getSLARecord(requestId).catch(() => null as EscalationSLA | null),
      getAuditTrail(requestId).catch(() => [] as ApprovalAuditRecord[]),
      getApprovalTimeline(requestId).catch(() => [] as ApprovalTimelineEvent[]),
      this.getDecisionsForRequest(requestId),
    ]);

    return {
      request,
      evidence,
      justification,
      expiry,
      sla,
      auditTrail,
      timeline,
      decisions,
    };
  }

  /** Get approval decisions for a request from the database */
  private async getDecisionsForRequest(requestId: string): Promise<ApprovalDecision[]> {
    const records = await db.hitlApprovalDecision.findMany({
      where: { requestId },
      orderBy: { decidedAt: "asc" },
    });

    return records.map((r) => ({
      id: r.id,
      requestId: r.requestId,
      decision: r.decision as "approved" | "rejected",
      decisionBy: r.decisionBy,
      decisionByName: r.decisionByName,
      role: r.role,
      comment: r.comment,
      delegatedFrom: r.delegatedFrom,
      decidedAt: r.decidedAt.toISOString(),
    }));
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let coordinatorInstance: HITLCoordinator | null = null;

export function getHITLCoordinator(): HITLCoordinator {
  if (!coordinatorInstance) {
    coordinatorInstance = HITLCoordinator.getInstance();
  }
  return coordinatorInstance;
}

export function resetHITLCoordinator(): void {
  coordinatorInstance = null;
}
