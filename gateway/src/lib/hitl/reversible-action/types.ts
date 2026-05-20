// ─── Zenic-Agents v3 — HITL Reversible Action Types ──────────────────
// Phase 5: Re-exported types for the reversible-action module.

// Re-export shared types used by this module
export type {
  UndoAction,
  UndoRequestInput,
  CompensatingActionDescriptor,
  ApprovalRequest,
} from "../types";

export {
  ApprovalRequestStatus,
  UndoType,
  UndoStatus,
  HitlEventType,
} from "../types";
