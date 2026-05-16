// ─── Zenic-Agents v3 — HITL Reversible Action System ─────────────────
// Phase 5: Compensating action registry, undo execution, state snapshots
//
// Design Patterns:
//   - Memento: Snapshot capture before action execution
//   - Registry: CompensatingActionRegistry maps action→undo
//   - Strategy: Pluggable undo execution strategies per action type

import { db } from "@/lib/db";
import {
  type UndoAction,
  type UndoRequestInput,
  type CompensatingActionDescriptor,
  type ApprovalRequest,
  ApprovalRequestStatus,
  UndoType,
  UndoStatus,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";
import { notifyApprovalEvent } from "./notifications";

// ═══════════════════════════════════════════════════════════════════════════
// Compensating Action Registry
// ═══════════════════════════════════════════════════════════════════════════

class CompensatingActionRegistry {
  private static instance: CompensatingActionRegistry | null = null;
  private registry: Map<string, CompensatingActionDescriptor> = new Map();

  private constructor() {
    this.registerDefaults();
  }

  static getInstance(): CompensatingActionRegistry {
    if (!CompensatingActionRegistry.instance) {
      CompensatingActionRegistry.instance = new CompensatingActionRegistry();
    }
    return CompensatingActionRegistry.instance;
  }

  /** Register a compensating action descriptor for an action type */
  register(descriptor: CompensatingActionDescriptor): void {
    this.registry.set(descriptor.actionType, descriptor);
  }

  /** Get a compensating action descriptor by action type */
  get(actionType: string): CompensatingActionDescriptor | undefined {
    return this.registry.get(actionType);
  }

  /** Check if an action type has a registered compensating action */
  has(actionType: string): boolean {
    return this.registry.has(actionType);
  }

  /** List all registered action types */
  listRegistered(): string[] {
    return Array.from(this.registry.keys());
  }

  /** Generate undo payload for an action using registered descriptor */
  generateUndoPayload(actionType: string, actionPayload: Record<string, unknown>): Record<string, unknown> {
    const descriptor = this.registry.get(actionType);
    if (!descriptor) {
      // Default: return inverse payload
      return { _originalAction: actionType, _inverse: true, ...actionPayload };
    }
    return descriptor.generateUndoPayload(actionPayload);
  }

  /** Capture state snapshot before action execution */
  async captureSnapshot(actionType: string, actionPayload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const descriptor = this.registry.get(actionType);
    if (!descriptor) {
      return { _capturedAt: new Date().toISOString(), _actionType: actionType, actionPayload };
    }
    try {
      return await descriptor.captureSnapshot(actionPayload);
    } catch {
      return { _capturedAt: new Date().toISOString(), _actionType: actionType, actionPayload };
    }
  }

  /** Execute undo for an action using registered descriptor */
  async executeUndo(
    actionType: string,
    undoPayload: Record<string, unknown>,
    snapshot: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const descriptor = this.registry.get(actionType);
    if (!descriptor) {
      // No registered undo handler — return stub result
      return { _undoExecuted: false, _reason: "No registered compensating action", actionType };
    }
    return descriptor.executeUndo(undoPayload, snapshot);
  }

  /** Check if an action is truly reversible */
  isReversible(actionType: string): boolean {
    const descriptor = this.registry.get(actionType);
    return descriptor?.isReversible ?? true;
  }

  /** Get irreversibility reason */
  getIrreversibilityReason(actionType: string): string | undefined {
    const descriptor = this.registry.get(actionType);
    return descriptor?.irreversibilityReason;
  }

  /** Register default compensating actions */
  private registerDefaults(): void {
    // Database operation — reversible via DELETE/UPDATE
    this.register({
      actionType: "database_write",
      description: "Database write operation — undo via reverse write",
      isReversible: true,
      defaultUndoWindowMs: 3600000, // 1 hour
      generateUndoPayload: (payload) => ({
        _operation: "reverse_write",
        _originalPayload: payload,
        table: payload.table,
        operation: payload.operation === "insert" ? "delete" : payload.operation === "delete" ? "insert" : "update",
        key: payload.key,
      }),
      captureSnapshot: async (payload) => ({
        _capturedAt: new Date().toISOString(),
        table: payload.table,
        key: payload.key,
        operation: payload.operation,
      }),
      executeUndo: async (undoPayload, snapshot) => ({
        _undoExecuted: true,
        _operation: undoPayload._operation,
        table: undoPayload.table,
        key: undoPayload.key,
        snapshotBefore: snapshot,
      }),
    });

    // Configuration change — reversible via previous config restore
    this.register({
      actionType: "config_change",
      description: "Configuration change — undo via previous config restore",
      isReversible: true,
      defaultUndoWindowMs: 7200000, // 2 hours
      generateUndoPayload: (payload) => ({
        _operation: "restore_config",
        _originalPayload: payload,
        configPath: payload.configPath,
        previousValue: payload.previousValue,
      }),
      captureSnapshot: async (payload) => ({
        _capturedAt: new Date().toISOString(),
        configPath: payload.configPath,
        currentValue: payload.currentValue,
      }),
      executeUndo: async (undoPayload, snapshot) => ({
        _undoExecuted: true,
        configPath: undoPayload.configPath,
        restoredValue: undoPayload.previousValue,
        previousSnapshot: snapshot,
      }),
    });

    // Deployment — reversible via rollback
    this.register({
      actionType: "deployment",
      description: "Deployment — undo via rollback to previous version",
      isReversible: true,
      defaultUndoWindowMs: 1800000, // 30 minutes
      generateUndoPayload: (payload) => ({
        _operation: "rollback_deployment",
        _originalPayload: payload,
        service: payload.service,
        targetVersion: payload.previousVersion,
      }),
      captureSnapshot: async (payload) => ({
        _capturedAt: new Date().toISOString(),
        service: payload.service,
        currentVersion: payload.currentVersion,
      }),
      executeUndo: async (undoPayload, snapshot) => ({
        _undoExecuted: true,
        service: undoPayload.service,
        rolledBackTo: undoPayload.targetVersion,
        snapshotBefore: snapshot,
      }),
    });

    // Email sent — IRREVERSIBLE
    this.register({
      actionType: "email_send",
      description: "Email sent — cannot be undone once delivered",
      isReversible: false,
      irreversibilityReason: "Email cannot be recalled once delivered to recipient",
      defaultUndoWindowMs: 0,
      generateUndoPayload: () => ({ _irreversible: true }),
      captureSnapshot: async () => ({ _irreversible: true }),
      executeUndo: async () => ({ _undoExecuted: false, _reason: "Irreversible action" }),
    });

    // Notification sent — IRREVERSIBLE
    this.register({
      actionType: "notification_send",
      description: "Push notification sent — cannot be undone",
      isReversible: false,
      irreversibilityReason: "Push notification cannot be recalled once delivered",
      defaultUndoWindowMs: 0,
      generateUndoPayload: () => ({ _irreversible: true }),
      captureSnapshot: async () => ({ _irreversible: true }),
      executeUndo: async () => ({ _undoExecuted: false, _reason: "Irreversible action" }),
    });

    // Policy change — reversible via policy rollback
    this.register({
      actionType: "policy_change",
      description: "Policy change — undo via version rollback",
      isReversible: true,
      defaultUndoWindowMs: 86400000, // 24 hours
      generateUndoPayload: (payload) => ({
        _operation: "rollback_policy",
        _originalPayload: payload,
        policyId: payload.policyId,
        previousVersion: payload.previousVersion,
      }),
      captureSnapshot: async (payload) => ({
        _capturedAt: new Date().toISOString(),
        policyId: payload.policyId,
        currentVersion: payload.currentVersion,
      }),
      executeUndo: async (undoPayload, snapshot) => ({
        _undoExecuted: true,
        policyId: undoPayload.policyId,
        rolledBackTo: undoPayload.previousVersion,
        snapshotBefore: snapshot,
      }),
    });

    // Financial transaction — reversible via compensating transaction
    this.register({
      actionType: "financial_transfer",
      description: "Financial transfer — undo via reverse transfer",
      isReversible: true,
      defaultUndoWindowMs: 1800000, // 30 minutes
      generateUndoPayload: (payload) => ({
        _operation: "reverse_transfer",
        _originalPayload: payload,
        fromAccount: payload.toAccount,
        toAccount: payload.fromAccount,
        amount: payload.amount,
        currency: payload.currency,
      }),
      captureSnapshot: async (payload) => ({
        _capturedAt: new Date().toISOString(),
        fromAccount: payload.fromAccount,
        toAccount: payload.toAccount,
        amount: payload.amount,
      }),
      executeUndo: async (undoPayload, snapshot) => ({
        _undoExecuted: true,
        reverseTransfer: {
          from: undoPayload.fromAccount,
          to: undoPayload.toAccount,
          amount: undoPayload.amount,
        },
        snapshotBefore: snapshot,
      }),
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Reversible Action Service
// ═══════════════════════════════════════════════════════════════════════════

class ReversibleActionService {
  private static instance: ReversibleActionService | null = null;

  private constructor() {}

  static getInstance(): ReversibleActionService {
    if (!ReversibleActionService.instance) {
      ReversibleActionService.instance = new ReversibleActionService();
    }
    return ReversibleActionService.instance;
  }

  /** Execute an approved action with automatic undo registration */
  async executeApprovedAction(requestId: string): Promise<{
    success: boolean;
    executionResult: Record<string, unknown>;
    snapshot: Record<string, unknown>;
  }> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (record.status !== ApprovalRequestStatus.APPROVED) {
      throw new Error(`Cannot execute action for request in status "${record.status}"`);
    }

    if (record.executedAt) {
      throw new Error(`Action for request "${requestId}" has already been executed`);
    }

    const actionPayload = JSON.parse(record.actionPayload) as Record<string, unknown>;
    const actionType = record.targetAction;
    const registry = CompensatingActionRegistry.getInstance();

    // Capture state snapshot before execution
    let snapshot: Record<string, unknown>;
    try {
      snapshot = await registry.captureSnapshot(actionType, actionPayload);
    } catch {
      snapshot = { _capturedAt: new Date().toISOString(), _actionType: actionType, actionPayload };
    }

    // Check if the action is irreversible
    const isReversible = record.isReversible && registry.isReversible(actionType);

    // Compute undo deadline
    const descriptor = registry.get(actionType);
    const undoWindowMs = descriptor?.defaultUndoWindowMs ?? 3600000;
    const undoDeadline = isReversible && undoWindowMs > 0
      ? new Date(Date.now() + undoWindowMs)
      : null;

    // Execute the action (stub — in production this would dispatch to the real action executor)
    const executionResult: Record<string, unknown> = {
      _executed: true,
      _actionType: actionType,
      _executedAt: new Date().toISOString(),
      targetResource: record.targetResource,
      actionPayload,
    };

    // Update the request with execution results
    await db.hitlApprovalRequest.update({
      where: { requestId },
      data: {
        executedAt: new Date(),
        executionResult: JSON.stringify(executionResult),
        isReversible,
        undoDeadline,
        ...(isReversible ? {} : { status: ApprovalRequestStatus.IRREVERSIBLE }),
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.EXECUTED,
      actorId: "system",
      actorName: "System",
      details: {
        actionType,
        isReversible,
        undoDeadline: undoDeadline?.toISOString(),
        snapshotKeys: Object.keys(snapshot),
      },
    });

    // If reversible, notify that undo is available
    if (isReversible && undoDeadline) {
      await notifyApprovalEvent("undo_available", {
        requestId,
        title: record.title,
        undoDeadline: undoDeadline.toISOString(),
        requesterId: record.requesterId,
      });
    }

    return { success: true, executionResult, snapshot };
  }

  /** Undo an approved action */
  async undoAction(requestId: string, input: UndoRequestInput): Promise<UndoAction> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!record) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    if (!record.isReversible) {
      throw new Error(`Action for request "${requestId}" is not reversible`);
    }

    if (!record.executedAt) {
      throw new Error(`Action for request "${requestId}" has not been executed yet`);
    }

    if (record.undoExecutedAt) {
      throw new Error(`Action for request "${requestId}" has already been undone`);
    }

    // Check undo deadline
    if (record.undoDeadline && new Date() > record.undoDeadline) {
      throw new Error(`Undo window for request "${requestId}" has expired`);
    }

    const actionType = record.targetAction;
    const registry = CompensatingActionRegistry.getInstance();
    const undoPayload = JSON.parse(record.undoPayload) as Record<string, unknown>;

    // Get snapshot from existing undo action or create one
    const existingUndo = await db.hitlUndoAction.findFirst({
      where: { requestId, status: UndoStatus.PENDING },
    });

    const snapshotBefore = existingUndo
      ? JSON.parse(existingUndo.snapshotBefore) as Record<string, unknown>
      : { _capturedAt: record.executedAt.toISOString(), _actionType: actionType };

    // Execute the undo
    const undoType = input.undoType ?? UndoType.FULL_UNDO;
    let undoResult: Record<string, unknown>;

    try {
      undoResult = await registry.executeUndo(actionType, undoPayload, snapshotBefore);
    } catch (error) {
      // Undo execution failed
      const failedUndo = await db.hitlUndoAction.create({
        data: {
          requestId,
          undoType,
          undoBy: input.undoBy,
          undoByName: input.undoByName,
          reason: input.reason,
          snapshotBefore: JSON.stringify(snapshotBefore),
          undoPayload: JSON.stringify(undoPayload),
          undoResult: JSON.stringify({ _error: error instanceof Error ? error.message : "Unknown error" }),
          status: UndoStatus.FAILED,
        },
      });

      return this.mapUndoRecord(failedUndo);
    }

    // Mark the request as undone
    await db.hitlApprovalRequest.update({
      where: { requestId },
      data: {
        status: ApprovalRequestStatus.UNDONE,
        undoExecutedAt: new Date(),
      },
    });

    // Create undo action record
    const undoActionRecord = await db.hitlUndoAction.create({
      data: {
        requestId,
        undoType,
        undoBy: input.undoBy,
        undoByName: input.undoByName,
        reason: input.reason,
        snapshotBefore: JSON.stringify(snapshotBefore),
        undoPayload: JSON.stringify(undoPayload),
        undoResult: JSON.stringify(undoResult),
        status: UndoStatus.EXECUTED,
        executedAt: new Date(),
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: HitlEventType.UNDONE,
      actorId: input.undoBy,
      actorName: input.undoByName,
      details: {
        undoType,
        reason: input.reason,
        undoResultKeys: Object.keys(undoResult),
      },
    });

    // Notify
    await notifyApprovalEvent("approval_undone", {
      requestId,
      title: record.title,
      undoByName: input.undoByName,
      reason: input.reason,
      requesterId: record.requesterId,
    });

    return this.mapUndoRecord(undoActionRecord);
  }

  /** Check if an undo is still within the time window */
  async isUndoAvailable(requestId: string): Promise<{
    canUndo: boolean;
    reason?: string;
    undoDeadline?: string;
    timeRemaining?: number;
  }> {
    const record = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!record) {
      return { canUndo: false, reason: "Request not found" };
    }

    if (!record.isReversible) {
      return { canUndo: false, reason: "Action is not reversible" };
    }

    if (!record.executedAt) {
      return { canUndo: false, reason: "Action has not been executed" };
    }

    if (record.undoExecutedAt) {
      return { canUndo: false, reason: "Action has already been undone" };
    }

    if (record.status !== ApprovalRequestStatus.APPROVED && record.status !== ApprovalRequestStatus.IRREVERSIBLE) {
      return { canUndo: false, reason: `Request is in status "${record.status}"` };
    }

    if (record.undoDeadline) {
      const now = new Date();
      const deadline = new Date(record.undoDeadline);
      if (now > deadline) {
        return {
          canUndo: false,
          reason: "Undo window has expired",
          undoDeadline: deadline.toISOString(),
        };
      }

      return {
        canUndo: true,
        undoDeadline: deadline.toISOString(),
        timeRemaining: deadline.getTime() - now.getTime(),
      };
    }

    // No deadline means unlimited undo window
    return { canUndo: true };
  }

  /** Map undo action database record to domain model */
  private mapUndoRecord(record: {
    id: string;
    requestId: string;
    undoType: string;
    undoBy: string;
    undoByName: string;
    reason: string;
    snapshotBefore: string;
    undoPayload: string;
    undoResult: string | null;
    status: string;
    executedAt: Date | null;
    createdAt: Date;
  }): UndoAction {
    return {
      id: record.id,
      requestId: record.requestId,
      undoType: record.undoType as UndoType,
      undoBy: record.undoBy,
      undoByName: record.undoByName,
      reason: record.reason,
      snapshotBefore: JSON.parse(record.snapshotBefore),
      undoPayload: JSON.parse(record.undoPayload),
      undoResult: record.undoResult ? JSON.parse(record.undoResult) : null,
      status: record.status as UndoStatus,
      executedAt: record.executedAt?.toISOString() ?? null,
      createdAt: record.createdAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let reversibleServiceInstance: ReversibleActionService | null = null;
let registryInstance: CompensatingActionRegistry | null = null;

export function getReversibleActionService(): ReversibleActionService {
  if (!reversibleServiceInstance) {
    reversibleServiceInstance = ReversibleActionService.getInstance();
  }
  return reversibleServiceInstance;
}

export function getCompensatingActionRegistry(): CompensatingActionRegistry {
  if (!registryInstance) {
    registryInstance = CompensatingActionRegistry.getInstance();
  }
  return registryInstance;
}

export function resetReversibleActionService(): void {
  reversibleServiceInstance = null;
  registryInstance = null;
}
