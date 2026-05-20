// ─── Zenic-Agents v3 — Saga Orchestrator for Subscription Lifecycle ──────
// USDT TRC20 ONLY. All subscription lifecycle operations are managed as
// Sagas with compensating actions for rollback on failure.
//
// This module provides the DB-backed orchestration layer that:
// 1. Creates Saga executions from Rust engine definitions
// 2. Persists Saga state to the database
// 3. Executes steps sequentially with compensating rollback on failure
// 4. Pauses sagas awaiting external input (e.g. admin confirmation)
// 5. Resumes paused sagas when external input arrives

import { db } from "@/lib/db";
import { randomUUID } from "crypto";
import type { FeatureName } from "./types";
import { checkFeature, validateTrc20Address, calculatePricing, validateUpgradePath, validateDowngradePath, calculateProration } from "./wasm-bridge";

// ═══════════════════════════════════════════════════════════════════════════
// Saga Types
// ═══════════════════════════════════════════════════════════════════════════

export const SagaTypeName = {
  TRIAL_CREATION: "trial_creation",
  TRIAL_CONVERSION: "trial_conversion",
  PAYMENT_VERIFICATION: "payment_verification",
  CANCELLATION: "cancellation",
  RENEWAL: "renewal",
  UPGRADE: "upgrade",
  DOWNGRADE: "downgrade",
  REACTIVATION: "reactivation",
} as const;
export type SagaTypeName = (typeof SagaTypeName)[keyof typeof SagaTypeName];

export const SagaStatusName = {
  PENDING: "pending",
  RUNNING: "running",
  COMPLETED: "completed",
  COMPENSATING: "compensating",
  COMPENSATED: "compensated",
  FAILED: "failed",
  TIMED_OUT: "timed_out",
  PAUSED: "paused",
} as const;
export type SagaStatusName = (typeof SagaStatusName)[keyof typeof SagaStatusName];

export const SagaStepStatusName = {
  PENDING: "pending",
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
  COMPENSATING: "compensating",
  COMPENSATED: "compensated",
  SKIPPED: "skipped",
} as const;
export type SagaStepStatusName = (typeof SagaStepStatusName)[keyof typeof SagaStepStatusName];

export interface SagaStepResult {
  success: boolean;
  output?: Record<string, unknown>;
  error?: string;
}

export interface SagaOrchestratorResult {
  executionId: string;
  sagaType: SagaTypeName;
  status: SagaStatusName;
  currentStepIndex: number;
  totalSteps: number;
  completedSteps: number;
  errorMessage?: string;
  compensationReason?: string;
  steps: Array<{
    stepIndex: number;
    stepName: string;
    status: SagaStepStatusName;
    output?: Record<string, unknown>;
    error?: string;
  }>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Step Action Handlers
// Each handler performs a DB operation and returns a SagaStepResult.
// On failure, the compensating action will be called for rollback.
// ═══════════════════════════════════════════════════════════════════════════

type StepHandler = (input: Record<string, unknown>) => Promise<SagaStepResult>;
type CompensationHandler = (input: Record<string, unknown>, stepOutput: Record<string, unknown>) => Promise<void>;

const stepHandlers: Record<string, StepHandler> = {
  // ─── Validation Steps ──────────────────────────────────────────────────

  async validate_email_uniqueness(input) {
    const { email } = input as { email: string };
    if (!email || !email.includes("@")) {
      return { success: false, error: "Invalid email format" };
    }
    // Check if tenant already has a subscription (one per tenant)
    const existing = await db.subscription.findFirst({
      where: { tenantId: input.tenantId as string },
    });
    if (existing) {
      return { success: false, error: "Tenant already has a subscription" };
    }
    return { success: true, output: { email_valid: true } };
  },

  async validate_trc20_address(input) {
    const { address } = input as { address: string };
    const result = validateTrc20Address(address || "");
    if (!result.valid) {
      return { success: false, error: result.reason };
    }
    return { success: true, output: { wallet_valid: true, address } };
  },

  async validate_subscription_status(input) {
    const { tenantId, expectedStatus } = input as { tenantId: string; expectedStatus: string };
    const subscription = await db.subscription.findUnique({ where: { tenantId } });
    if (!subscription) {
      return { success: false, error: `No subscription found for tenant ${tenantId}` };
    }
    if (subscription.status !== expectedStatus) {
      return { success: false, error: `Subscription status is '${subscription.status}', expected '${expectedStatus}'` };
    }
    return { success: true, output: { subscriptionId: subscription.subscriptionId, currentTier: subscription.tier } };
  },

  async validate_trc20_tx_hash(input) {
    const { txHash } = input as { txHash: string };
    if (!txHash || txHash.length !== 64 || !/^[a-fA-F0-9]{64}$/.test(txHash)) {
      return { success: false, error: "Invalid TRC20 transaction hash: must be 64 hex characters" };
    }
    return { success: true, output: { tx_hash_valid: true } };
  },

  async check_tx_hash_uniqueness(input) {
    const { txHash } = input as { txHash: string };
    const existing = await db.subscriptionPayment.findFirst({ where: { txHash } });
    if (existing) {
      return { success: false, error: "TRC20 transaction hash already used (double-spend prevention)" };
    }
    return { success: true, output: { tx_hash_unique: true } };
  },

  async validate_subscription_cancellable(input) {
    const { tenantId } = input as { tenantId: string };
    const subscription = await db.subscription.findUnique({ where: { tenantId } });
    if (!subscription) return { success: false, error: "No subscription found" };
    if (subscription.status === "cancelled") return { success: false, error: "Subscription already cancelled" };
    if (subscription.status === "expired") return { success: false, error: "Subscription already expired" };
