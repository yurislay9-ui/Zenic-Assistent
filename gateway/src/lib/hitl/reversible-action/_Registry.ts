// ─── Compensating Action Registry ──────────────────────────────────────
// Registry pattern: maps action types to compensating action descriptors.
// Extracted from reversible-action.ts for modularity.

import type { CompensatingActionDescriptor } from "../types";
import { registerDefaults } from "./_registry-defaults";

class CompensatingActionRegistry {
  private static instance: CompensatingActionRegistry | null = null;
  private registry: Map<string, CompensatingActionDescriptor> = new Map();

  private constructor() {
    registerDefaults(this);
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
}

export { CompensatingActionRegistry };
