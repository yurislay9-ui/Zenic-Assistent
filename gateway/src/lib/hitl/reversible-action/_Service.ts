// ─── Reversible Action Service ─────────────────────────────────────────
// Execute approved actions and undo them with state snapshots.
// Extracted from reversible-action.ts for modularity.

import { db } from "@/lib/db";
import {
  type UndoAction,
  type UndoRequestInput,
  ApprovalRequestStatus,
  UndoType,
  UndoStatus,
  HitlEventType,
} from "../types";
import { recordAuditEvent } from "../approval-audit";
import { notifyApprovalEvent } from "../notifications";
import { CompensatingActionRegistry } from "./_Registry";

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

    let snapshot: Record<string, unknown>;
    try {
      snapshot = await registry.captureSnapshot(actionType, actionPayload);
    } catch {
      snapshot = { _capturedAt: new Date().toISOString(), _actionType: actionType, actionPayload };
    }

    const isReversible = record.isReversible && registry.isReversible(actionType);

    const descriptor = registry.get(actionType);
    const undoWindowMs = descriptor?.defaultUndoWindowMs ?? 3600000;
    const undoDeadline = isReversible && undoWindowMs > 0
      ? new Date(Date.now() + undoWindowMs)
      : null;

    const executionResult: Record<string, unknown> = {
      _executed: true,
      _actionType: actionType,
      _executedAt: new Date().toISOString(),
      targetResource: record.targetResource,
      actionPayload,
    };

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

    if (record.undoDeadline && new Date() > record.undoDeadline) {
      throw new Error(`Undo window for request "${requestId}" has expired`);
    }

    const actionType = record.targetAction;
    const registry = CompensatingActionRegistry.getInstance();
    const undoPayload = JSON.parse(record.undoPayload) as Record<string, unknown>;

    const existingUndo = await db.hitlUndoAction.findFirst({
      where: { requestId, status: UndoStatus.PENDING },
    });

    const snapshotBefore = existingUndo
      ? JSON.parse(existingUndo.snapshotBefore) as Record<string, unknown>
      : { _capturedAt: record.executedAt.toISOString(), _actionType: actionType };

    const undoType = input.undoType ?? UndoType.FULL_UNDO;
    let undoResult: Record<string, unknown>;

    try {
      undoResult = await registry.executeUndo(actionType, undoPayload, snapshotBefore);
    } catch (error) {
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

    await db.hitlApprovalRequest.update({
      where: { requestId },
      data: {
        status: ApprovalRequestStatus.UNDONE,
        undoExecutedAt: new Date(),
      },
    });

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

export { ReversibleActionService };
