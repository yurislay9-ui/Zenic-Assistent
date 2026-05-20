// ─── HITL Coordinator (Facade + Singleton) ──────────────────────────────
// Central orchestrator for all HITL operations.
// Extracted from hitl-coordinator.ts for modularity.

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
} from "../types";
import { getApprovalEngine } from "../approval-engine";
import { getEvidenceService } from "../evidence-service";
import { getJustificationService } from "../justification-service";
import { getExpiryService } from "../expiry-service";
import { getSLAService } from "../sla-service";
import { getReversibleActionService } from "../reversible-action";
import { notifyApprovalEvent } from "../notifications";
import { getNotificationLogService } from "../notification-log-service";
import { recordAuditEvent, getAuditTrail, getApprovalTimeline } from "../approval-audit";
import { recordCoordinatorAudit, notifyAndLog, getRequestOrThrow } from "./_notification-helpers";
import { processExpired, processSLABreaches, processExpiryNotifications } from "./_process-methods";

class HITLCoordinator {
  private static instance: HITLCoordinator | null = null;

  private constructor() {}

  static getInstance(): HITLCoordinator {
    if (!HITLCoordinator.instance) {
      HITLCoordinator.instance = new HITLCoordinator();
    }
    return HITLCoordinator.instance;
  }

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

    const request = await engine.createRequest(input);

    const evidence: ApprovalEvidence[] = [];
    if (input.evidence && input.evidence.length > 0) {
      for (const ev of input.evidence) {
        const attached = await evidenceService.attachEvidence(request.requestId, ev);
        evidence.push(attached);
      }
    }

    let justification: ApprovalJustification | null = null;
    if (input.justification) {
      justification = await justificationService.provideJustification(
        request.requestId,
        input.justification,
      );
    }

    const expiry = await expiryService.setExpiry(request.requestId, {
      expiresAt: input.deadline ?? undefined,
      autoRevertEnabled: input.autoRevertOnExpiry ?? true,
      revertAction: input.revertAction ?? input.undoPayload,
      notificationSchedule: input.expiryNotificationSchedule,
    });

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

    const existingRequest = await getRequestOrThrow(requestId);

    const validation = justificationService.validateJustification(
      justificationInput,
      existingRequest.priority,
    );
    if (!validation.valid) {
      throw new Error(`Justification validation failed: ${validation.errors.join("; ")}`);
    }

    const justification = await justificationService.provideJustification(
      requestId,
      justificationInput,
      existingRequest.priority,
    );

    const request = await engine.approveRequest(requestId, approveInput);

    let executionResult: { success: boolean; executionResult: Record<string, unknown>; snapshot: Record<string, unknown> } | undefined;
    if (request.status === "approved" && !request.executedAt) {
      try {
        const result = await reversibleService.executeApprovedAction(requestId);
        executionResult = result;
      } catch (error) {
        console.error(
          `[HITLCoordinator] Action execution failed for ${requestId}:`,
          error instanceof Error ? error.message : "Unknown error",
        );
      }
    }

    try {
      await expiryService.cancelExpiry(requestId);
    } catch {
      // Expiry record may not exist
    }

    await recordCoordinatorAudit(requestId, HitlEventType.APPROVED, approveInput.decisionBy, approveInput.decisionByName, {
      action: "full_approve",
      justificationId: justification.justificationId,
      executed: !!executionResult,
      executionSuccess: executionResult?.success,
    });

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
      // Non-critical
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

    const existingRequest = await getRequestOrThrow(requestId);

    const validation = justificationService.validateJustification(
      justificationInput,
      existingRequest.priority,
    );
    if (!validation.valid) {
      throw new Error(`Justification validation failed: ${validation.errors.join("; ")}`);
    }

    const justification = await justificationService.provideJustification(
      requestId,
      justificationInput,
      existingRequest.priority,
    );

    const request = await engine.rejectRequest(requestId, rejectInput);

    try {
      await expiryService.cancelExpiry(requestId);
    } catch {
      // Expiry record may not exist
    }

    await recordCoordinatorAudit(requestId, HitlEventType.REJECTED, rejectInput.decisionBy, rejectInput.decisionByName, {
      action: "full_reject",
      justificationId: justification.justificationId,
      reason: rejectInput.comment,
    });

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
      // Non-critical
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

    const undoAction = await reversibleService.undoAction(requestId, undoInput);

    let expiryCancelled = false;
    try {
      expiryCancelled = await expiryService.cancelExpiry(requestId);
    } catch {
      // Expiry record may not exist
    }

    await recordCoordinatorAudit(requestId, HitlEventType.UNDONE, undoInput.undoBy, undoInput.undoByName, {
      action: "full_undo",
      undoType: undoInput.undoType ?? "full_undo",
      reason: undoInput.reason,
      expiryCancelled,
    });

    await notifyApprovalEvent("approval_undone", {
      requestId,
      undoByName: undoInput.undoByName,
      reason: undoInput.reason,
    });

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
      // Non-critical
    }

    return { undoAction, expiryCancelled };
  }

  /** Delegate to extracted process methods */
  async processExpired() { return processExpired(); }
  async processSLABreaches() { return processSLABreaches(); }
  async processExpiryNotifications() { return processExpiryNotifications(); }

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

    const [evidence, justification, expiry, sla, auditTrail, timeline, decisions] = await Promise.all([
      evidenceService.getEvidence(requestId).catch(() => [] as ApprovalEvidence[]),
      justificationService.getJustification(requestId).catch(() => null as ApprovalJustification | null),
      expiryService.getExpiryRecord(requestId).catch(() => null as ExpiryRecord | null),
      slaService.getSLARecord(requestId).catch(() => null as EscalationSLA | null),
      getAuditTrail(requestId).catch(() => [] as ApprovalAuditRecord[]),
      getApprovalTimeline(requestId).catch(() => [] as ApprovalTimelineEvent[]),
      this.getDecisionsForRequest(requestId),
    ]);

    return { request, evidence, justification, expiry, sla, auditTrail, timeline, decisions };
  }

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
