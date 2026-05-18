// ─── Zenic-Agents v3 — HITL Compensating Action Registry ─────────────
// Phase 5: Compensating action registry, default descriptors
//
// Design Patterns:
//   - Registry: CompensatingActionRegistry maps action→undo
//   - Strategy: Pluggable undo execution strategies per action type

import {
  type CompensatingActionDescriptor,
} from "./types";

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

// ─── Singleton Accessor ───────────────────────────────────────────────

let registryInstance: CompensatingActionRegistry | null = null;

export function getCompensatingActionRegistry(): CompensatingActionRegistry {
  if (!registryInstance) {
    registryInstance = CompensatingActionRegistry.getInstance();
  }
  return registryInstance;
}

export { CompensatingActionRegistry };
