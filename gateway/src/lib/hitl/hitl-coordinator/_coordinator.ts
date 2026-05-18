// ─── Zenic-Agents v3 — HITL Coordinator (Core) ────────────────────────
// Phase 5: Central orchestrator — Facade pattern (core approval methods)
//
// Contains: createFullRequest, fullApprove, fullReject,
//           getFullRequestDetails, getDecisionsForRequest

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
  HitlEventType,
} from "../types";
import { getApprovalEngine } from "../approval-engine";
import { getEvidenceService } from "../evidence-service";
import { getJustificationService } from "../justification-service";
import { getExpiryService } from "../expiry-service";
import { getSLAService } from "../sla-service";
import { getReversibleActionService } from "../reversible-action";
import { getNotificationLogService } from "../notification-log-service";
import { recordAuditEvent, getAuditTrail, getApprovalTimeline } from "../approval-audit";
import type {
  CreateFullRequestResult,
  FullApproveResult,
  FullRejectResult,
  FullRequestDetailsResult,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// HITL Coordinator (Facade + Singleton) — Core Methods
// ═══════════════════════════════════════════════════════════════════════════

export class HITLCoordinator {
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
  async createFullRequest(input: ExtendedCreateApprovalRequestInput): Promise<CreateFullRequestResult> {
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
  ): Promise<FullApproveResult> {
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
  ): Promise<FullRejectResult> {
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

  /** Get full request details with all related data */
  async getFullRequestDetails(requestId: string): Promise<FullRequestDetailsResult> {
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
  async getDecisionsForRequest(requestId: string): Promise<ApprovalDecision[]> {
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

// ─── Singleton Accessor ───────────────────────────────────────────────

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
