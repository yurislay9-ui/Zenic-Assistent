// ─── Zenic-Agents v3 — HITL Approval Engine ──────────────────────────
// Phase 5: Core approval request lifecycle management
//
// Design Patterns:
//   - Singleton: Single engine instance via getApprovalEngine()
//   - Strategy: ApprovalPolicyStrategy for pluggable approval policies
//   - Observer: Emits events to NotificationService on state changes

import { db } from "@/lib/db";
import {
  type CreateApprovalRequestInput,
  type ApprovalRequest,
  type ApprovalListOptions,
  ApprovalRequestStatus,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import {
  executeCreateRequest,
  executeApproveRequest,
  executeRejectRequest,
} from "./_routing";
import {
  queryGetRequest,
  queryListRequests,
  queryCheckExpiredRequests,
  queryGetStats,
  queryListPendingForUser,
  queryGetHistory,
  mapDbRecordToModel,
  type DbApprovalRecord,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// Approval Engine (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class ApprovalEngine {
  private static instance: ApprovalEngine | null = null;

  private constructor() {}

  static getInstance(): ApprovalEngine {
    if (!ApprovalEngine.instance) {
      ApprovalEngine.instance = new ApprovalEngine();
    }
    return ApprovalEngine.instance;
  }

  // ─── Mutation Methods ────────────────────────────────────────────────

  /** Create a new approval request */
  async createRequest(input: CreateApprovalRequestInput): Promise<ApprovalRequest> {
    return executeCreateRequest(input);
  }

  /** Approve a request */
  async approveRequest(requestId: string, input: import("../types").ApproveRequestInput): Promise<ApprovalRequest> {
    return executeApproveRequest(requestId, input);
  }

  /** Reject a request */
  async rejectRequest(requestId: string, input: import("../types").RejectRequestInput): Promise<ApprovalRequest> {
    return executeRejectRequest(requestId, input);
  }

  /** Update a request (e.g., modify details before approval) */
  async updateRequest(
    requestId: string,
    updates: Partial<Pick<CreateApprovalRequestInput, "title" | "description" | "priority" | "deadline" | "tags" | "metadata">>,
  ): Promise<ApprovalRequest> {
    const record = await db.hitlApprovalRequest.findUnique({ where: { requestId } });
    if (!record) throw new Error(`Approval request "${requestId}" not found`);
    if (record.status !== ApprovalRequestStatus.PENDING) {
      throw new Error(`Cannot update request in status "${record.status}"`);
    }

    const data: Record<string, unknown> = {};
    if (updates.title !== undefined) data.title = updates.title;
    if (updates.description !== undefined) data.description = updates.description;
    if (updates.priority !== undefined) data.priority = updates.priority;
    if (updates.deadline !== undefined) data.deadline = updates.deadline ? new Date(updates.deadline) : null;
    if (updates.tags !== undefined) data.tags = JSON.stringify(updates.tags);
    if (updates.metadata !== undefined) data.metadata = JSON.stringify(updates.metadata);

    const updated = await db.hitlApprovalRequest.update({ where: { requestId }, data });
    return mapDbRecordToModel(updated as unknown as DbApprovalRecord);
  }

  /** Cancel a pending request */
  async cancelRequest(requestId: string, cancelledBy: string, cancelledByName: string): Promise<ApprovalRequest> {
    const record = await db.hitlApprovalRequest.findUnique({ where: { requestId } });
    if (!record) throw new Error(`Approval request "${requestId}" not found`);
    if (record.status !== ApprovalRequestStatus.PENDING) {
      throw new Error(`Cannot cancel request in status "${record.status}"`);
    }

    const updated = await db.hitlApprovalRequest.update({
      where: { requestId },
      data: { status: ApprovalRequestStatus.CANCELLED },
    });

    await recordAuditEvent({
      requestId, eventType: HitlEventType.CANCELLED,
      actorId: cancelledBy, actorName: cancelledByName,
      details: { previousStatus: record.status },
    });

    return mapDbRecordToModel(updated as unknown as DbApprovalRecord);
  }

  // ─── Query Method Delegates ──────────────────────────────────────────

  /** Get an approval request by ID */
  async getRequest(requestId: string): Promise<ApprovalRequest | null> {
    return queryGetRequest(requestId);
  }

  /** List approval requests with filtering and pagination */
  async listRequests(options: ApprovalListOptions = {}): Promise<{
    data: ApprovalRequest[]; total: number; page: number; pageSize: number;
  }> {
    return queryListRequests(options);
  }

  /** Check for expired requests and mark them */
  async checkExpiredRequests(): Promise<number> {
    return queryCheckExpiredRequests();
  }

  /** Get approval statistics */
  async getStats() {
    return queryGetStats();
  }

  /** List pending approvals for a specific user */
  async listPendingForUser(userId: string): Promise<ApprovalRequest[]> {
    return queryListPendingForUser(userId);
  }

  /** Get approval history with filters */
  async getHistory(options: ApprovalListOptions & { userId?: string }): Promise<{
    data: ApprovalRequest[]; total: number; page: number; pageSize: number;
  }> {
    return queryGetHistory(options);
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let engineInstance: ApprovalEngine | null = null;

export function getApprovalEngine(): ApprovalEngine {
  if (!engineInstance) {
    engineInstance = ApprovalEngine.getInstance();
  }
  return engineInstance;
}

export function resetApprovalEngine(): void {
  engineInstance = null;
  ApprovalEngine.instance = null;
}
