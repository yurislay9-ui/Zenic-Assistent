// ─── Zenic-Agents v3 — HITL Delegation & Escalation ──────────────────
// Phase 5: Delegate approvals, auto-escalation, delegation rules
//
// Design Patterns:
//   - Chain of Responsibility: Escalation chain handlers
//   - Strategy: Delegation depth/validity strategies
//   - Observer: Notifies on delegation/escalation events

import { db } from "@/lib/db";
import {
  type DelegateRequestInput,
  type EscalateRequestInput,
  type Delegation,
  type DelegationRule,
  type CreateDelegationRuleInput,
  type Escalation,
  ApprovalRequestStatus,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";
import { notifyApprovalEvent } from "./notifications";

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

// ═══════════════════════════════════════════════════════════════════════════
// Escalation Service (Chain of Responsibility Pattern)
// ═══════════════════════════════════════════════════════════════════════════

/** Escalation level configuration */
interface EscalationLevelConfig {
  level: number;
  role: string;
  timeoutMs: number;
}

const DEFAULT_ESCALATION_CHAIN: EscalationLevelConfig[] = [
  { level: 0, role: "reviewer", timeoutMs: 0 },           // Direct approver
  { level: 1, role: "team_lead", timeoutMs: 3600000 },    // 1 hour
  { level: 2, role: "director", timeoutMs: 7200000 },     // 2 hours
  { level: 3, role: "c_suite", timeoutMs: 14400000 },     // 4 hours
];

class EscalationService {
  private static instance: EscalationService | null = null;
  private escalationChain: EscalationLevelConfig[];

  private constructor(escalationChain?: EscalationLevelConfig[]) {
    this.escalationChain = escalationChain ?? DEFAULT_ESCALATION_CHAIN;
  }

  static getInstance(): EscalationService {
    if (!EscalationService.instance) {
      EscalationService.instance = new EscalationService();
    }
    return EscalationService.instance;
  }

  /** Escalate an approval request to the next level */
  async escalateRequest(requestId: string, input: EscalateRequestInput): Promise<Escalation> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
      include: { escalations: true },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (record.status !== ApprovalRequestStatus.PENDING &&
        record.status !== ApprovalRequestStatus.DELEGATED &&
        record.status !== ApprovalRequestStatus.ESCALATED) {
      throw new Error(`Cannot escalate request in status "${record.status}"`);
    }

    const currentLevel = record.escalationLevel;
    const nextLevel = currentLevel + 1;

    // Check if we've exceeded the escalation chain
    const maxLevel = this.escalationChain.length - 1;
    if (nextLevel > maxLevel) {
      throw new Error(`Maximum escalation level (${maxLevel}) already reached`);
    }

    // Create the escalation record
    const escalation = await db.hitlEscalation.create({
      data: {
        requestId,
        fromLevel: currentLevel,
        toLevel: nextLevel,
        fromUserId: input.fromUserId ?? null,
        toUserId: input.toUserId ?? null,
        toRole: input.toRole,
        reason: input.reason ?? "",
        autoEscalated: false,
      },
    });

    // Update the request
    await db.hitlApprovalRequest.update({
      where: { requestId },
      data: {
        escalationLevel: nextLevel,
        status: ApprovalRequestStatus.ESCALATED,
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.ESCALATED,
      actorId: input.fromUserId ?? "system",
      actorName: input.fromUserId ? "User" : "System",
      details: {
        fromLevel: currentLevel,
        toLevel: nextLevel,
        toRole: input.toRole,
        reason: input.reason,
        autoEscalated: false,
      },
    });

    // Notify
    await notifyApprovalEvent("approval_escalated", {
      requestId,
      title: record.title,
      priority: record.priority,
      fromLevel: currentLevel,
      toLevel: nextLevel,
      toRole: input.toRole,
      reason: input.reason,
    });

    return this.mapEscalationRecord(escalation);
  }

  /** Check for requests that need auto-escalation based on timeout
   *  FIX #13: Añadido take con límite para evitar cargar todos los pendientes.
   */
  async checkAutoEscalation(): Promise<number> {
    const now = new Date();
    let escalatedCount = 0;

    // Find requests that are pending or already escalated and may need further escalation
    const candidates = await db.hitlApprovalRequest.findMany({
      where: {
        status: { in: [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.ESCALATED] },
      },
      include: { escalations: true },
      take: 100, // INVARIANT 3: max 100 por batch
    });

    for (const record of candidates) {
      const currentLevel = record.escalationLevel;
      const nextLevel = currentLevel + 1;

      // Check if next level exists in chain
      const nextLevelConfig = this.escalationChain.find((l) => l.level === nextLevel);
      if (!nextLevelConfig) continue;

      // Calculate timeout for current level
      const currentLevelConfig = this.escalationChain.find((l) => l.level === currentLevel);
      if (!currentLevelConfig || currentLevelConfig.timeoutMs === 0) continue;

      // Check if the timeout has elapsed
      const lastEscalation = record.escalations
        .filter((e) => e.toLevel === currentLevel)
        .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())[0];

      const referenceTime = lastEscalation
        ? lastEscalation.createdAt
        : record.createdAt;

      const elapsedMs = now.getTime() - referenceTime.getTime();

      if (elapsedMs >= currentLevelConfig.timeoutMs) {
        // Auto-escalate
        await db.hitlEscalation.create({
          data: {
            requestId: record.requestId,
            fromLevel: currentLevel,
            toLevel: nextLevel,
            fromUserId: null,
            toUserId: null,
            toRole: nextLevelConfig.role,
            reason: `Auto-escalated: no action within ${Math.round(currentLevelConfig.timeoutMs / 60000)} minutes`,
            autoEscalated: true,
          },
        });

        await db.hitlApprovalRequest.update({
          where: { requestId: record.requestId },
          data: {
            escalationLevel: nextLevel,
            status: ApprovalRequestStatus.ESCALATED,
          },
        });

        await recordAuditEvent({
          requestId: record.requestId,
          eventType: HitlEventType.ESCALATED,
          actorId: "system",
          actorName: "System",
          details: {
            fromLevel: currentLevel,
            toLevel: nextLevel,
            toRole: nextLevelConfig.role,
            autoEscalated: true,
            elapsedMs,
            timeoutMs: currentLevelConfig.timeoutMs,
          },
        });

        await notifyApprovalEvent("approval_escalated", {
          requestId: record.requestId,
          title: record.title,
          priority: record.priority,
          fromLevel: currentLevel,
          toLevel: nextLevel,
          toRole: nextLevelConfig.role,
          autoEscalated: true,
        });

        escalatedCount++;
      }
    }

    return escalatedCount;
  }

  /** Get escalation history for a request
   *  FIX #7: Añadido take con límite.
   */
  async getEscalationHistory(requestId: string, limit = 50): Promise<Escalation[]> {
    const escalations = await db.hitlEscalation.findMany({
      where: { requestId },
      orderBy: { createdAt: "asc" },
      take: Math.min(limit, 200), // INVARIANT 3
    });

    return escalations.map((e) => this.mapEscalationRecord(e));
  }

  private mapEscalationRecord(record: {
    id: string;
    requestId: string;
    fromLevel: number;
    toLevel: number;
    fromUserId: string | null;
    toUserId: string | null;
    toRole: string;
    reason: string;
    autoEscalated: boolean;
    createdAt: Date;
  }): Escalation {
    return {
      id: record.id,
      requestId: record.requestId,
      fromLevel: record.fromLevel,
      toLevel: record.toLevel,
      fromUserId: record.fromUserId,
      toUserId: record.toUserId,
      toRole: record.toRole,
      reason: record.reason,
      autoEscalated: record.autoEscalated,
      createdAt: record.createdAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let delegationServiceInstance: DelegationService | null = null;
let escalationServiceInstance: EscalationService | null = null;

export function getDelegationService(): DelegationService {
  if (!delegationServiceInstance) {
    delegationServiceInstance = DelegationService.getInstance();
  }
  return delegationServiceInstance;
}

export function getEscalationService(): EscalationService {
  if (!escalationServiceInstance) {
    escalationServiceInstance = EscalationService.getInstance();
  }
  return escalationServiceInstance;
}

export function resetDelegationService(): void {
  delegationServiceInstance = null;
  // FIX #8: Solo resetea Delegación, NO Escalation.
  // Nota: DelegationService.instance es private, se resetea indirectamente
  // porque getInstance() crea nueva instancia cuando delegationServiceInstance = null
}

export function resetEscalationService(): void {
  escalationServiceInstance = null;
}
