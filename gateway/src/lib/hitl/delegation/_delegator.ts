// ─── Zenic-Agents v3 — HITL Delegation Service ───────────────────────
// Phase 5: Delegate approvals, delegation chain validation
//
// Design Patterns:
//   - Strategy: Delegation depth/validity strategies
//   - Observer: Notifies on delegation events

import { db } from "@/lib/db";
import {
  type DelegateRequestInput,
  type Delegation,
  type DelegationRule,
  type CreateDelegationRuleInput,
  ApprovalRequestStatus,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";

// ═══════════════════════════════════════════════════════════════════════════
// Delegation Service
// ═══════════════════════════════════════════════════════════════════════════

class DelegationService {
  private static instance: DelegationService | null = null;

  /** Maximum delegation chain depth */
  private readonly MAX_DELEGATION_DEPTH = 5;

  private constructor() {}

  static getInstance(): DelegationService {
    if (!DelegationService.instance) {
      DelegationService.instance = new DelegationService();
    }
    return DelegationService.instance;
  }

  /** Delegate an approval request to another user */
  async delegateRequest(requestId: string, input: DelegateRequestInput): Promise<Delegation> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
      include: { delegations: true },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (record.status !== ApprovalRequestStatus.PENDING && record.status !== ApprovalRequestStatus.ESCALATED) {
      throw new Error(`Cannot delegate request in status "${record.status}"`);
    }

    // Prevent self-delegation
    if (input.fromUserId === input.toUserId) {
      throw new Error("Cannot delegate to yourself");
    }

    // Check delegation chain depth
    const chainDepth = this.calculateDelegationDepth(record.delegations, input.fromUserId);
    if (chainDepth >= this.MAX_DELEGATION_DEPTH) {
      throw new Error(`Maximum delegation depth (${this.MAX_DELEGATION_DEPTH}) exceeded`);
    }

    // Check if target user already has a delegation for this request
    const existingDelegation = record.delegations.find(
      (d) => d.toUserId === input.toUserId && d.isActive,
    );
    if (existingDelegation) {
      throw new Error(`User "${input.toUserName}" already has an active delegation for this request`);
    }

    // Create the delegation
    const expiresAt = input.expiresAt ? new Date(input.expiresAt) : null;

    const delegation = await db.hitlDelegation.create({
      data: {
        requestId,
        fromUserId: input.fromUserId,
        fromUserName: input.fromUserName,
        toUserId: input.toUserId,
        toUserName: input.toUserName,
        reason: input.reason ?? "",
        expiresAt,
        isActive: true,
      },
    });

    // Update the request status to delegated
    await db.hitlApprovalRequest.update({
      where: { requestId },
      data: { status: ApprovalRequestStatus.DELEGATED },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.DELEGATED,
      actorId: input.fromUserId,
      actorName: input.fromUserName,
      details: {
        toUserId: input.toUserId,
        toUserName: input.toUserName,
        reason: input.reason,
        expiresAt: expiresAt?.toISOString(),
        chainDepth: chainDepth + 1,
      },
    });

    // Notify the delegate
    await notifyApprovalEvent("approval_delegated", {
      requestId,
      title: record.title,
      priority: record.priority,
      fromUserName: input.fromUserName,
      toUserId: input.toUserId,
      toUserName: input.toUserName,
      reason: input.reason,
    });

    return this.mapDelegationRecord(delegation);
  }

  /** Calculate the current delegation chain depth for a user */
  private calculateDelegationDepth(
    delegations: Array<{ fromUserId: string; toUserId: string; isActive: boolean }>,
    userId: string,
  ): number {
    const activeDelegations = delegations.filter((d) => d.isActive);
    let depth = 0;
    let currentUserId = userId;

    // Walk the chain backwards
    for (let i = 0; i < this.MAX_DELEGATION_DEPTH; i++) {
      const incoming = activeDelegations.find((d) => d.toUserId === currentUserId);
      if (!incoming) break;
      depth++;
      currentUserId = incoming.fromUserId;
    }

    return depth;
  }

  /** Get all active delegations for a user */
  async getActiveDelegationsForUser(userId: string): Promise<Delegation[]> {
    const delegations = await db.hitlDelegation.findMany({
      where: {
        OR: [{ fromUserId: userId }, { toUserId: userId }],
        isActive: true,
      },
      orderBy: { createdAt: "desc" },
    });

    return delegations.map((d) => this.mapDelegationRecord(d));
  }

  /** Revoke a delegation */
  async revokeDelegation(delegationId: string, revokedBy: string): Promise<void> {
    const delegation = await db.hitlDelegation.findUnique({
      where: { id: delegationId },
    });

    if (!delegation) {
      throw new Error(`Delegation "${delegationId}" not found`);
    }

    if (!delegation.isActive) {
      throw new Error("Delegation is already inactive");
    }

    if (delegation.fromUserId !== revokedBy) {
      throw new Error("Only the delegator can revoke a delegation");
    }

    await db.hitlDelegation.update({
      where: { id: delegationId },
      data: { isActive: false },
    });

    // Check if the request should revert to pending
    const remainingActive = await db.hitlDelegation.count({
      where: { requestId: delegation.requestId, isActive: true },
    });

    if (remainingActive === 0) {
      const request = await db.hitlApprovalRequest.findUnique({
        where: { requestId: delegation.requestId },
      });

      if (request && request.status === ApprovalRequestStatus.DELEGATED) {
        await db.hitlApprovalRequest.update({
          where: { requestId: delegation.requestId },
          data: { status: ApprovalRequestStatus.PENDING },
        });
      }
    }
  }

  /** List delegation rules
   *  FIX #7: Añadido take con límite para evitar cargar todas las reglas.
   */
  async listDelegationRules(options?: { fromUserId?: string; isActive?: boolean; limit?: number }): Promise<DelegationRule[]> {
    const where: Record<string, unknown> = {};
    if (options?.fromUserId) where.fromUserId = options.fromUserId;
    if (options?.isActive !== undefined) where.isActive = options.isActive;

    const limit = Math.min(options?.limit ?? 100, 200); // INVARIANT 3

    const rules = await db.hitlDelegationRule.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: limit,
    });

    return rules.map((r) => this.mapDelegationRuleRecord(r));
  }

  /** Create a standing delegation rule */
  async createDelegationRule(input: CreateDelegationRuleInput): Promise<DelegationRule> {
    if (input.fromUserId === input.toUserId) {
      throw new Error("Cannot create a delegation rule to yourself");
    }

    const maxDepth = input.maxDepth ?? 1;
    if (maxDepth > this.MAX_DELEGATION_DEPTH) {
      throw new Error(`Maximum delegation depth is ${this.MAX_DELEGATION_DEPTH}`);
    }

    const expiresAt = input.expiresAt ? new Date(input.expiresAt) : null;

    const rule = await db.hitlDelegationRule.create({
      data: {
        fromUserId: input.fromUserId,
        toUserId: input.toUserId,
        toUserName: input.toUserName,
        ruleName: input.ruleName,
        description: input.description ?? "",
        isActive: true,
        maxDepth,
        expiresAt,
      },
    });

    return this.mapDelegationRuleRecord(rule);
  }

  /** Deactivate a delegation rule */
  async deactivateDelegationRule(ruleId: string): Promise<void> {
    await db.hitlDelegationRule.update({
      where: { id: ruleId },
      data: { isActive: false },
    });
  }

  private mapDelegationRecord(record: {
    id: string;
    requestId: string;
    fromUserId: string;
    fromUserName: string;
    toUserId: string;
    toUserName: string;
    reason: string;
    expiresAt: Date | null;
    isActive: boolean;
    createdAt: Date;
  }): Delegation {
    return {
      id: record.id,
      requestId: record.requestId,
      fromUserId: record.fromUserId,
      fromUserName: record.fromUserName,
      toUserId: record.toUserId,
      toUserName: record.toUserName,
      reason: record.reason,
      expiresAt: record.expiresAt?.toISOString() ?? null,
      isActive: record.isActive,
      createdAt: record.createdAt.toISOString(),
    };
  }

  private mapDelegationRuleRecord(record: {
    id: string;
    fromUserId: string;
    toUserId: string;
    toUserName: string;
    ruleName: string;
    description: string;
    isActive: boolean;
    maxDepth: number;
    expiresAt: Date | null;
    createdAt: Date;
    updatedAt: Date;
  }): DelegationRule {
    return {
      id: record.id,
      fromUserId: record.fromUserId,
      toUserId: record.toUserId,
      toUserName: record.toUserName,
      ruleName: record.ruleName,
      description: record.description,
      isActive: record.isActive,
      maxDepth: record.maxDepth,
      expiresAt: record.expiresAt?.toISOString() ?? null,
      createdAt: record.createdAt.toISOString(),
      updatedAt: record.updatedAt.toISOString(),
    };
  }
}

// ─── Singleton Accessor ───────────────────────────────────────────────

let delegationServiceInstance: DelegationService | null = null;

export function getDelegationService(): DelegationService {
  if (!delegationServiceInstance) {
    delegationServiceInstance = DelegationService.getInstance();
  }
  return delegationServiceInstance;
}

export function resetDelegationService(): void {
  delegationServiceInstance = null;
  // FIX #8: Solo resetea Delegación, NO Escalation.
  // Nota: DelegationService.instance es private, se resetea indirectamente
  // porque getInstance() crea nueva instancia cuando delegationServiceInstance = null
}

export { DelegationService };
