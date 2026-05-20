// ─── Compensating Action Registry Defaults ─────────────────────────────
// Default compensating action descriptors for built-in action types.
// Extracted from reversible-action.ts for modularity.

import type { CompensatingActionDescriptor } from "../types";

/** Register default compensating actions into the registry */
export function registerDefaults(registry: {
  register: (descriptor: CompensatingActionDescriptor) => void;
}): void {
  // Database operation — reversible via DELETE/UPDATE
  registry.register({
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
  registry.register({
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
  registry.register({
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
  registry.register({
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
  registry.register({
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
  registry.register({
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
  registry.register({
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
