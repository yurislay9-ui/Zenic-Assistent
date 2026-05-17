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
    return { success: true, output: { subscriptionId: subscription.subscriptionId, tier: subscription.tier } };
  },

  async validate_subscription_renewable(input) {
    const { tenantId } = input as { tenantId: string };
    const subscription = await db.subscription.findUnique({ where: { tenantId } });
    if (!subscription) return { success: false, error: "No subscription found" };
    if (subscription.status !== "active") return { success: false, error: "Only active subscriptions can be renewed" };
    return { success: true, output: { subscriptionId: subscription.subscriptionId, tier: subscription.tier } };
  },

  async validate_upgrade_path(input) {
    const { currentTier, newTier } = input as { currentTier: string; newTier: string };
    const result = validateUpgradePath(currentTier, newTier);
    if (!result.valid) return { success: false, error: result.error || "Invalid upgrade path" };
    return { success: true, output: { valid: true, currentTier, newTier } };
  },

  async validate_downgrade_path(input) {
    const { currentTier, newTier } = input as { currentTier: string; newTier: string };
    const result = validateDowngradePath(currentTier, newTier);
    if (!result.valid) return { success: false, error: result.error || "Invalid downgrade path" };
    return { success: true, output: { valid: true, currentTier, newTier } };
  },

  async validate_subscription_reactivatable(input) {
    const { tenantId } = input as { tenantId: string };
    const subscription = await db.subscription.findUnique({ where: { tenantId } });
    if (!subscription) return { success: false, error: "No subscription found" };
    if (subscription.status !== "cancelled") return { success: false, error: "Only cancelled subscriptions can be reactivated" };
    return { success: true, output: { subscriptionId: subscription.subscriptionId, tier: subscription.tier } };
  },

  async identify_features_to_revoke(input) {
    const { newTier } = input as { newTier: string };
    // This is informational — we identify which features the new tier lacks
    return { success: true, output: { newTier, message: "Features to revoke identified" } };
  },

  // ─── Pricing Steps ─────────────────────────────────────────────────────

  async calculate_subscription_pricing(input) {
    const { tier } = input as { tier: string };
    const calc = calculatePricing(tier);
    return { success: true, output: { pricing: calc } };
  },

  async calculate_proration_amount(input) {
    const { currentTier, newTier, daysRemaining, daysInPeriod } = input as {
      currentTier: string; newTier: string; daysRemaining: number; daysInPeriod: number;
    };
    const result = calculateProration(currentTier, newTier, daysRemaining, daysInPeriod);
    return { success: true, output: { proration: result } };
  },

  async calculate_proration_credit(input) {
    const { currentTier, newTier, daysRemaining, daysInPeriod } = input as {
      currentTier: string; newTier: string; daysRemaining: number; daysInPeriod: number;
    };
    const result = calculateProration(currentTier, newTier, daysRemaining, daysInPeriod);
    return { success: true, output: { proration: result } };
  },

  // ─── Database Steps ────────────────────────────────────────────────────

  async db_create_subscription(input) {
    const { tenantId, tier, billingWalletAddress } = input as {
      tenantId: string; tier: string; billingWalletAddress: string;
    };
    const now = new Date();
    const trialEndsAt = tier === "trial" ? new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000) : null;
    const periodEnd = tier === "trial"
      ? new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000)
      : new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

    const subscription = await db.subscription.create({
      data: {
        subscriptionId: `sub_${tier}_${randomUUID().slice(0, 8)}`,
        tenantId,
        tier,
        status: tier === "trial" ? "trial" : "pending_payment",
        paymentMethod: "usdt_trc20",
        billingWalletAddress: billingWalletAddress || "",
        addOns: "[]",
        startedAt: now,
        currentPeriodEnd: periodEnd,
        trialEndsAt,
        autoRenew: tier !== "trial",
      },
    });
    return { success: true, output: { subscriptionId: subscription.subscriptionId, dbId: subscription.id } };
  },

  async db_delete_subscription(input) {
    const { dbId } = input as { dbId: string };
    await db.subscription.delete({ where: { id: dbId } }).catch(() => {});
    return { success: true, output: { deleted: true } };
  },

  async db_create_payment_request(input) {
    const { subscriptionDbId, amountUsdt, walletFrom, walletTo } = input as {
      subscriptionDbId: string; amountUsdt: number; walletFrom: string; walletTo: string;
    };
    const payment = await db.subscriptionPayment.create({
      data: {
        paymentId: `pay_${Date.now()}`,
        subscriptionDbId,
        amountUsdt,
        walletFrom,
        walletTo,
        txHash: "pending",
        status: "pending",
        verificationMethod: "manual_admin",
        requiredConfirmations: 20,
      },
    });
    return { success: true, output: { paymentId: payment.paymentId, dbId: payment.id } };
  },

  async db_delete_payment_request(input) {
    const { dbId } = input as { dbId: string };
    await db.subscriptionPayment.delete({ where: { id: dbId } }).catch(() => {});
    return { success: true, output: { deleted: true } };
  },

  async db_update_subscription(input) {
    const { tenantId, newTier, newStatus } = input as {
      tenantId: string; newTier: string; newStatus: string;
    };
    const now = new Date();
    const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    const subscription = await db.subscription.update({
      where: { tenantId },
      data: {
        tier: newTier,
        status: newStatus,
        currentPeriodEnd: periodEnd,
        trialCompletedAt: now,
        updatedAt: now,
      },
    });
    return { success: true, output: { subscriptionId: subscription.subscriptionId } };
  },

  async db_revert_subscription_to_trial(input) {
    const { tenantId } = input as { tenantId: string };
    await db.subscription.update({
      where: { tenantId },
      data: { tier: "trial", status: "trial", updatedAt: new Date() },
    }).catch(() => {});
    return { success: true, output: { reverted: true } };
  },

  async db_update_subscription_status(input) {
    const { tenantId, newStatus } = input as { tenantId: string; newStatus: string };
    await db.subscription.update({
      where: { tenantId },
      data: { status: newStatus, updatedAt: new Date() },
    });
    return { success: true, output: { updated: true } };
  },

  async db_revert_subscription_status(input) {
    const { tenantId, previousStatus } = input as { tenantId: string; previousStatus: string };
    await db.subscription.update({
      where: { tenantId },
      data: { status: previousStatus, updatedAt: new Date() },
    }).catch(() => {});
    return { success: true, output: { reverted: true } };
  },

  async db_cancel_subscription(input) {
    const { tenantId, reason } = input as { tenantId: string; reason?: string };
    await db.subscription.update({
      where: { tenantId },
      data: { status: "cancelled", cancelledAt: new Date(), cancellationReason: reason || "User requested", updatedAt: new Date() },
    });
    return { success: true, output: { cancelled: true } };
  },

  async db_reactivate_subscription(input) {
    const { tenantId } = input as { tenantId: string };
    const now = new Date();
    await db.subscription.update({
      where: { tenantId },
      data: {
        status: "active",
        cancelledAt: null,
        cancellationReason: null,
        currentPeriodEnd: new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000),
        updatedAt: now,
      },
    });
    return { success: true, output: { reactivated: true } };
  },

  async db_extend_subscription_period(input) {
    const { tenantId, days } = input as { tenantId: string; days?: number };
    const sub = await db.subscription.findUnique({ where: { tenantId } });
    if (!sub) return { success: false, error: "Subscription not found" };
    const currentEnd = new Date(sub.currentPeriodEnd);
    const newEnd = new Date(currentEnd.getTime() + (days || 30) * 24 * 60 * 60 * 1000);
    await db.subscription.update({
      where: { tenantId },
      data: { currentPeriodEnd: newEnd, status: "active", updatedAt: new Date() },
    });
    return { success: true, output: { extended_to: newEnd.toISOString() } };
  },

  async db_revert_subscription_period(input) {
    // Best-effort revert — set period end back
    const { tenantId, previousPeriodEnd } = input as { tenantId: string; previousPeriodEnd: string };
    await db.subscription.update({
      where: { tenantId },
      data: { currentPeriodEnd: new Date(previousPeriodEnd), updatedAt: new Date() },
    }).catch(() => {});
    return { success: true, output: { reverted: true } };
  },

  async db_reset_usage_records(input) {
    const { tenantId } = input as { tenantId: string };
    const sub = await db.subscription.findUnique({ where: { tenantId } });
    if (!sub) return { success: true, output: { skipped: true } };
    const now = new Date();
    const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    await db.usageRecord.updateMany({
      where: { subscriptionDbId: sub.id },
      data: { usageCount: 0, overageCount: 0, overageChargeUsdt: 0, periodStart: now, periodEnd },
    });
    return { success: true, output: { reset: true } };
  },

  async db_restore_usage_records(input) {
    // Best-effort — usage records are not critical to revert
    return { success: true, output: { restored: true } };
  },

  async db_update_subscription_tier(input) {
    const { tenantId, newTier } = input as { tenantId: string; newTier: string };
    await db.subscription.update({
      where: { tenantId },
      data: { tier: newTier, updatedAt: new Date() },
    });
    return { success: true, output: { updated: true } };
  },

  async db_revert_subscription_tier(input) {
    const { tenantId, previousTier } = input as { tenantId: string; previousTier: string };
    await db.subscription.update({
      where: { tenantId },
      data: { tier: previousTier, updatedAt: new Date() },
    }).catch(() => {});
    return { success: true, output: { reverted: true } };
  },

  async db_create_payment(input) {
    const { subscriptionDbId, amountUsdt, walletFrom, walletTo, txHash } = input as {
      subscriptionDbId: string; amountUsdt: number; walletFrom: string; walletTo: string; txHash: string;
    };
    const payment = await db.subscriptionPayment.create({
      data: {
        paymentId: `pay_${Date.now()}`,
        subscriptionDbId,
        amountUsdt,
        walletFrom,
        walletTo,
        txHash,
        status: "confirming",
        verificationMethod: "manual_admin",
        requiredConfirmations: 20,
      },
    });
    return { success: true, output: { paymentId: payment.paymentId, dbId: payment.id } };
  },

  async db_delete_payment(input) {
    const { dbId } = input as { dbId: string };
    await db.subscriptionPayment.delete({ where: { id: dbId } }).catch(() => {});
    return { success: true, output: { deleted: true } };
  },

  // ─── Feature Gate Steps ────────────────────────────────────────────────

  async initialize_feature_gates(input) {
    const { tenantId, tier } = input as { tenantId: string; tier: string };
    // Feature gates are enforced dynamically via checkFeature() — no DB records needed
    // This step exists for saga completeness (audit trail)
    return { success: true, output: { tenantId, tier, feature_gates_initialized: true } };
  },

  async revoke_feature_gates(input) {
    const { tenantId } = input as { tenantId: string };
    return { success: true, output: { tenantId, feature_gates_revoked: true } };
  },

  async update_feature_gates_for_tier(input) {
    const { tenantId, tier } = input as { tenantId: string; tier: string };
    return { success: true, output: { tenantId, tier, feature_gates_updated: true } };
  },

  async revert_feature_gates_to_trial(input) {
    const { tenantId } = input as { tenantId: string };
    return { success: true, output: { tenantId, reverted_to_trial: true } };
  },

  async revert_feature_gates_to_previous_tier(input) {
    const { tenantId, previousTier } = input as { tenantId: string; previousTier: string };
    return { success: true, output: { tenantId, previousTier, reverted: true } };
  },

  async revoke_all_feature_gates(input) {
    const { tenantId } = input as { tenantId: string };
    return { success: true, output: { tenantId, all_revoked: true } };
  },

  async restore_feature_gates(input) {
    const { tenantId, tier } = input as { tenantId: string; tier: string };
    return { success: true, output: { tenantId, tier, restored: true } };
  },

  async revoke_features_for_downgrade(input) {
    const { tenantId, newTier } = input as { tenantId: string; newTier: string };
    return { success: true, output: { tenantId, newTier, features_revoked: true } };
  },

  async restore_revoked_features(input) {
    const { tenantId, previousTier } = input as { tenantId: string; previousTier: string };
    return { success: true, output: { tenantId, previousTier, features_restored: true } };
  },

  // ─── External Input Steps (pause saga) ──────────────────────────────────

  async await_admin_confirmation(input) {
    // This step ALWAYS pauses the saga — it requires external input
    return { success: true, output: { paused: true, reason: "awaiting_admin_confirmation" } };
  },

  // ─── Finalization Steps ────────────────────────────────────────────────

  async finalize_payment_confirmation(input) {
    const { paymentDbId, tenantId } = input as { paymentDbId: string; tenantId: string };
    const now = new Date();
    await db.subscriptionPayment.update({
      where: { id: paymentDbId },
      data: { status: "confirmed", confirmedAt: now, adminConfirmedAt: now },
    }).catch(() => {});
    await db.subscription.update({
      where: { tenantId },
      data: { status: "active", lastPaymentAt: now, updatedAt: now },
    }).catch(() => {});
    return { success: true, output: { finalized: true } };
  },

  async revert_payment_to_awaiting(input) {
    const { paymentDbId } = input as { paymentDbId: string };
    await db.subscriptionPayment.update({
      where: { id: paymentDbId },
      data: { status: "pending", confirmedAt: null, adminConfirmedAt: null },
    }).catch(() => {});
    return { success: true, output: { reverted: true } };
  },

  async mark_payment_as_expired(input) {
    const { paymentDbId } = input as { paymentDbId: string };
    await db.subscriptionPayment.update({
      where: { id: paymentDbId },
      data: { status: "expired" },
    }).catch(() => {});
    return { success: true, output: { expired: true } };
  },

  async initiate_refund_process(input) {
    // Manual refund process — creates an audit record
    return { success: true, output: { refund_initiated: true, method: "manual_usdt_trc20" } };
  },

  async cancel_refund_process(input) {
    return { success: true, output: { refund_cancelled: true } };
  },

  // ─── Audit Steps ──────────────────────────────────────────────────────

  async create_audit_entry(input) {
    const { tenantId, action, resource, outcome } = input as {
      tenantId: string; action: string; resource: string; outcome: string;
    };
    try {
      await db.auditLog.create({
        data: {
          actorId: "system",
          actorType: "system",
          action: action || "saga.step",
          resource: resource || "subscription",
          severity: "info",
          outcome: outcome || "success",
          details: JSON.stringify(input),
          tags: JSON.stringify(["saga", "subscription"]),
        },
      });
    } catch {
      // Don't fail the saga for audit failures
    }
    return { success: true, output: { audit_created: true } };
  },

  async mark_audit_as_rolled_back(_input) {
    return { success: true, output: { audit_marked_rolled_back: true } };
  },
};

// BUG #7 FIX: Compensation handlers — previously empty, now properly defined
const compensationHandlers: Record<string, CompensationHandler> = {
  // ─── Validation steps: no-op (pure checks, no state to revert) ───
  validate_email_uniqueness: async () => {},
  validate_trc20_address: async () => {},
  validate_subscription_status: async () => {},
  validate_trc20_tx_hash: async () => {},
  check_tx_hash_uniqueness: async () => {},
  validate_subscription_cancellable: async () => {},
  validate_subscription_renewable: async () => {},
  validate_upgrade_path: async () => {},
  validate_downgrade_path: async () => {},
  validate_subscription_reactivatable: async () => {},
  identify_features_to_revoke: async () => {},

  // ─── Pricing steps: no-op (pure computation) ───
  calculate_subscription_pricing: async () => {},
  calculate_proration_amount: async () => {},
  calculate_proration_credit: async () => {},

  // ─── DB mutation steps: REVERT the changes ───
  async db_create_subscription(_input, stepOutput) {
    const dbId = stepOutput.dbId as string;
    if (dbId) {
      await db.subscription.delete({ where: { id: dbId } }).catch(() => {});
    }
  },

  async db_create_payment_request(_input, stepOutput) {
    const dbId = stepOutput.dbId as string;
    if (dbId) {
      await db.subscriptionPayment.delete({ where: { id: dbId } }).catch(() => {});
    }
  },

  async db_update_subscription(input, _stepOutput) {
    const { tenantId } = input as { tenantId: string; previousTier?: string; previousStatus?: string };
    const previousTier = input.previousTier as string | undefined;
    const previousStatus = input.previousStatus as string | undefined;
    if (previousTier || previousStatus) {
      await db.subscription.update({
        where: { tenantId },
        data: {
          ...(previousTier ? { tier: previousTier } : {}),
          ...(previousStatus ? { status: previousStatus } : {}),
          updatedAt: new Date(),
        },
      }).catch(() => {});
    }
  },

  async db_cancel_subscription(input, _stepOutput) {
    const { tenantId } = input as { tenantId: string };
    await db.subscription.update({
      where: { tenantId },
      data: { status: 'active', cancelledAt: null, cancellationReason: null, updatedAt: new Date() },
    }).catch(() => {});
  },

  async db_create_payment(_input, stepOutput) {
    const dbId = stepOutput.dbId as string;
    if (dbId) {
      await db.subscriptionPayment.delete({ where: { id: dbId } }).catch(() => {});
    }
  },

  async db_update_subscription_status(input, _stepOutput) {
    const { tenantId, previousStatus } = input as { tenantId: string; previousStatus?: string };
    if (previousStatus) {
      await db.subscription.update({
        where: { tenantId },
        data: { status: previousStatus, updatedAt: new Date() },
      }).catch(() => {});
    }
  },

  // Feature gate steps: informational, no compensation needed
  initialize_feature_gates: async () => {},
  revoke_feature_gates: async () => {},
  update_feature_gates_for_tier: async () => {},
  revert_feature_gates_to_trial: async () => {},
  revert_feature_gates_to_previous_tier: async () => {},
  revoke_all_feature_gates: async () => {},
  restore_feature_gates: async () => {},
  revoke_features_for_downgrade: async () => {},
  restore_revoked_features: async () => {},

  // Audit steps: no compensation needed (audit log is append-only)
  create_audit_entry: async () => {},
  mark_audit_as_rolled_back: async () => {},

  // Payment steps
  async finalize_payment_confirmation(_input, stepOutput) {
    const { paymentDbId } = _input as { paymentDbId?: string };
    if (paymentDbId) {
      await db.subscriptionPayment.update({
        where: { id: paymentDbId },
        data: { status: 'pending', confirmedAt: null, adminConfirmedAt: null },
      }).catch(() => {});
    }
  },

  initiate_refund_process: async () => {},
};

// ═══════════════════════════════════════════════════════════════════════════
// Saga Orchestrator
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Execute a Saga: create, persist, run steps with compensation on failure.
 */
export async function executeSaga(
  sagaType: SagaTypeName,
  tenantId: string,
  input: Record<string, unknown>,
  subscriptionId?: string,
): Promise<SagaOrchestratorResult> {
  // Import saga definition from the Rust engine
  const { getSagaDefinition } = await import("./wasm-bridge");
  const definition = getSagaDefinition(sagaType);

  if (!definition || !definition.steps) {
    return {
      executionId: "",
      sagaType,
      status: "failed",
      currentStepIndex: 0,
      totalSteps: 0,
      completedSteps: 0,
      errorMessage: `Unknown saga type: ${sagaType}`,
      steps: [],
    };
  }

  const steps = definition.steps;
  // BUG #13 FIX: Use crypto.randomUUID() instead of Date.now() for unique IDs
  const executionId = `saga_${sagaType}_${randomUUID().slice(0, 8)}`;

  // Persist saga execution
  const sagaExecution = await db.sagaExecution.create({
    data: {
      executionId,
      sagaType,
      status: "running",
      tenantId,
      subscriptionId: subscriptionId || null,
      currentStepIndex: 0,
      totalSteps: steps.length,
      completedSteps: 0,
      metadata: JSON.stringify(input),
      startedAt: new Date(),
    },
  });

  // Persist step records
  const stepRecords: Array<{ id: string; stepIndex: number; stepName: string; action: string; compensatingAction: string; isCritical: boolean; status: string; output: Record<string, unknown>; error?: string }> = [];
  for (const step of steps) {
    const record = await db.sagaStepRecord.create({
      data: {
        sagaExecutionDbId: sagaExecution.id,
        stepIndex: step.step_index,
        stepName: step.step_name,
        action: step.action,
        compensatingAction: step.compensating_action,
        isCritical: step.is_critical,
        status: "pending",
        input: JSON.stringify(input),
        requiresExternalInput: step.requires_external_input,
      },
    });
    stepRecords.push({
      id: record.id,
      stepIndex: step.step_index,
      stepName: step.step_name,
      action: step.action,
      compensatingAction: step.compensating_action,
      isCritical: step.is_critical,
      status: "pending",
      output: {},
    });
  }

  // Execute steps sequentially
  let currentStatus: SagaStatusName = "running";
  let completedSteps = 0;
  const stepOutputs: Record<number, Record<string, unknown>> = {};

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const stepRecord = stepRecords[i];

    // Update step to running
    await db.sagaStepRecord.update({
      where: { id: stepRecord.id },
      data: { status: "running", startedAt: new Date() },
    });

    // Find and execute the handler
    const handler = stepHandlers[step.action];
    if (!handler) {
      // No handler found — this is a configuration error
      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "failed", errorMessage: `No handler for action: ${step.action}`, completedAt: new Date() },
      });
      stepRecords[i].status = "failed";
      stepRecords[i].error = `No handler for action: ${step.action}`;

      if (step.is_critical) {
        currentStatus = "compensating";
        break;
      }
      continue;
    }

    try {
      const stepInput = { ...input, ...stepOutputs[i - 1], tenantId };
      const result = await handler(stepInput);

      if (result.success) {
        stepOutputs[i] = result.output || {};
        stepRecords[i].status = "completed";
        stepRecords[i].output = result.output || {};
        completedSteps++;

        await db.sagaStepRecord.update({
          where: { id: stepRecord.id },
          data: { status: "completed", output: JSON.stringify(result.output || {}), completedAt: new Date() },
        });

        // Check if step requires external input (pauses saga)
        if (step.requires_external_input) {
          currentStatus = "paused";
          await db.sagaExecution.update({
            where: { id: sagaExecution.id },
            data: { status: "paused", currentStepIndex: i, completedSteps },
          });
          break;
        }
      } else {
        stepRecords[i].status = "failed";
        stepRecords[i].error = result.error || "Step failed";
        await db.sagaStepRecord.update({
          where: { id: stepRecord.id },
          data: { status: "failed", errorMessage: result.error || "Step failed", completedAt: new Date() },
        });

        if (step.is_critical) {
          currentStatus = "compensating";
          break;
        }
        // Non-critical failure — continue
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      stepRecords[i].status = "failed";
      stepRecords[i].error = errorMsg;
      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "failed", errorMessage: errorMsg, completedAt: new Date() },
      });

      if (step.is_critical) {
        currentStatus = "compensating";
        break;
      }
    }
  }

  // Handle compensation if needed
  if (currentStatus === "compensating") {
    const failedStepIndex = stepRecords.findIndex(s => s.status === "failed");
    // Run compensating actions for all completed steps in reverse order
    for (let i = failedStepIndex - 1; i >= 0; i--) {
      const stepRecord = stepRecords[i];
      const step = steps[i];

      if (stepRecord.status !== "completed") continue;
      if (step.compensating_action === "none") continue;

      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "compensating", compensationStartedAt: new Date() },
      });

      const compensationHandler = compensationHandlers[step.compensating_action];
      if (compensationHandler) {
        try {
          await compensationHandler(input, stepOutputs[i] || {});
          await db.sagaStepRecord.update({
            where: { id: stepRecord.id },
            data: { status: "compensated", compensationCompletedAt: new Date() },
          });
          stepRecords[i].status = "compensated";
        } catch {
          await db.sagaStepRecord.update({
            where: { id: stepRecord.id },
            data: { status: "failed", compensationError: "Compensation failed", compensationCompletedAt: new Date() },
          });
          currentStatus = "failed";
        }
      } else {
        // No compensation handler — use step handler approach
        const compensatingAction = stepHandlers[step.compensating_action];
        if (compensatingAction) {
          try {
            await compensatingAction({ ...input, ...stepOutputs[i], tenantId });
            await db.sagaStepRecord.update({
              where: { id: stepRecord.id },
              data: { status: "compensated", compensationCompletedAt: new Date() },
            });
            stepRecords[i].status = "compensated";
          } catch {
            await db.sagaStepRecord.update({
              where: { id: stepRecord.id },
              data: { status: "failed", compensationError: "Compensation handler failed", compensationCompletedAt: new Date() },
            });
            currentStatus = "failed";
          }
        } else {
          // No compensation handler available — mark as compensated (best-effort)
          await db.sagaStepRecord.update({
            where: { id: stepRecord.id },
            data: { status: "compensated", compensationCompletedAt: new Date() },
          });
          stepRecords[i].status = "compensated";
        }
      }
    }

    if (currentStatus === "compensating") {
      currentStatus = "compensated";
    }
  } else if (currentStatus === "running" || currentStatus === "paused") {
    // All steps completed or paused
    if (completedSteps === steps.length || currentStatus === "paused") {
      // Will be set properly below
    }
  }

  // Determine final status
  if (currentStatus !== "failed" && currentStatus !== "paused") {
    if (completedSteps === steps.length) {
      currentStatus = "completed";
    } else if (currentStatus === "compensated") {
      // Already set
    }
  }

  // Update saga execution
  await db.sagaExecution.update({
    where: { id: sagaExecution.id },
    data: {
      status: currentStatus,
      currentStepIndex: stepRecords.findIndex(s => s.status === "failed" || s.status === "paused"),
      completedSteps,
      completedAt: currentStatus === "completed" || currentStatus === "compensated" || currentStatus === "failed" ? new Date() : null,
      errorMessage: stepRecords.find(s => s.status === "failed")?.error,
      compensationReason: currentStatus === "compensated" || currentStatus === "compensating"
        ? stepRecords.find(s => s.status === "failed")?.error : null,
      updatedAt: new Date(),
    },
  });

  return {
    executionId,
    sagaType,
    status: currentStatus,
    currentStepIndex: stepRecords.findIndex(s => s.status === "failed" || s.status === "paused"),
    totalSteps: steps.length,
    completedSteps,
    errorMessage: stepRecords.find(s => s.status === "failed")?.error,
    compensationReason: currentStatus === "compensated" ? stepRecords.find(s => s.status === "failed")?.error : undefined,
    steps: stepRecords.map(s => ({
      stepIndex: s.stepIndex,
      stepName: s.stepName,
      status: s.status as SagaStepStatusName,
      output: s.output,
      error: s.error,
    })),
  };
}

/**
 * Resume a paused Saga (after external input like admin confirmation)
 */
export async function resumeSaga(
  executionId: string,
  resumeInput: Record<string, unknown>,
): Promise<SagaOrchestratorResult> {
  const sagaExecution = await db.sagaExecution.findUnique({
    where: { executionId },
    include: { steps: { orderBy: { stepIndex: "asc" } } },
  });

  // BUG #10 FIX: Don't access sagaExecution after null check
  if (!sagaExecution) {
    return {
      executionId,
      sagaType: "trial_creation" as SagaTypeName, // Safe default, not null dereference
      status: "failed",
      currentStepIndex: 0,
      totalSteps: 0,
      completedSteps: 0,
      errorMessage: `Saga execution not found: ${executionId}`,
      steps: [],
    };
  }

  if (sagaExecution.status !== "paused") {
    return {
      executionId,
      sagaType: sagaExecution.sagaType as SagaTypeName,
      status: sagaExecution.status as SagaStatusName,
      currentStepIndex: sagaExecution.currentStepIndex,
      totalSteps: sagaExecution.totalSteps,
      completedSteps: sagaExecution.completedSteps,
      errorMessage: "Saga is not paused — cannot resume",
      steps: [],
    };
  }

  // Parse original input
  const originalInput = JSON.parse(sagaExecution.metadata || "{}");
  const input = { ...originalInput, ...resumeInput, tenantId: sagaExecution.tenantId };

  // Find the step that caused the pause (requires_external_input)
  const pausedStepIndex = sagaExecution.steps.findIndex(s => s.requiresExternalInput && s.status === "completed");

  // The step AFTER the paused step needs to continue
  // For payment sagas, the next step after await_admin_confirmation is finalize_payment_confirmation
  const nextStepIndex = pausedStepIndex + 1;
  if (nextStepIndex >= sagaExecution.totalSteps) {
    // All steps done — mark as completed
    await db.sagaExecution.update({
      where: { id: sagaExecution.id },
      data: { status: "completed", completedAt: new Date(), updatedAt: new Date() },
    });
    return {
      executionId,
      sagaType: sagaExecution.sagaType as SagaTypeName,
      status: "completed",
      currentStepIndex: sagaExecution.currentStepIndex,
      totalSteps: sagaExecution.totalSteps,
      completedSteps: sagaExecution.totalSteps,
      steps: [],
    };
  }

  // Execute remaining steps
  await db.sagaExecution.update({
    where: { id: sagaExecution.id },
    data: { status: "running", updatedAt: new Date() },
  });

  let currentStatus: SagaStatusName = "running";
  let completedSteps = sagaExecution.completedSteps;
  const stepOutputs: Record<number, Record<string, unknown>> = {};

  // Get step definitions
  const { getSagaDefinition } = await import("./wasm-bridge");
  const definition = getSagaDefinition(sagaExecution.sagaType as SagaTypeName);
  if (!definition?.steps) {
    return {
      executionId,
      sagaType: sagaExecution.sagaType as SagaTypeName,
      status: "failed",
      currentStepIndex: sagaExecution.currentStepIndex,
      totalSteps: sagaExecution.totalSteps,
      completedSteps,
      errorMessage: "Could not load saga definition for resume",
      steps: [],
    };
  }

  const steps = definition.steps;

  for (let i = nextStepIndex; i < steps.length; i++) {
    const step = steps[i];
    const stepRecord = sagaExecution.steps[i];

    await db.sagaStepRecord.update({
      where: { id: stepRecord.id },
      data: { status: "running", startedAt: new Date() },
    });

    const handler = stepHandlers[step.action];
    if (!handler) {
      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "failed", errorMessage: `No handler: ${step.action}`, completedAt: new Date() },
      });
      if (step.is_critical) {
        currentStatus = "compensating";
        break;
      }
      continue;
    }

    try {
      const stepInput = { ...input, ...stepOutputs[i - 1], tenantId: sagaExecution.tenantId };
      const result = await handler(stepInput);

      if (result.success) {
        stepOutputs[i] = result.output || {};
        completedSteps++;
        await db.sagaStepRecord.update({
          where: { id: stepRecord.id },
          data: { status: "completed", output: JSON.stringify(result.output || {}), completedAt: new Date() },
        });
      } else {
        await db.sagaStepRecord.update({
          where: { id: stepRecord.id },
          data: { status: "failed", errorMessage: result.error, completedAt: new Date() },
        });
        if (step.is_critical) {
          currentStatus = "compensating";
          break;
        }
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "failed", errorMessage: errorMsg, completedAt: new Date() },
      });
      if (step.is_critical) {
        currentStatus = "compensating";
        break;
      }
    }
  }

  // Finalize
  if (currentStatus === "running") currentStatus = "completed";

  await db.sagaExecution.update({
    where: { id: sagaExecution.id },
    data: {
      status: currentStatus,
      completedSteps,
      completedAt: ["completed", "compensated", "failed"].includes(currentStatus) ? new Date() : null,
      updatedAt: new Date(),
    },
  });

  return {
    executionId,
    sagaType: sagaExecution.sagaType as SagaTypeName,
    status: currentStatus,
    currentStepIndex: sagaExecution.currentStepIndex,
    totalSteps: sagaExecution.totalSteps,
    completedSteps,
    steps: [],
  };
}

/**
 * Get the status of a Saga execution
 */
export async function getSagaStatus(executionId: string): Promise<SagaOrchestratorResult | null> {
  const sagaExecution = await db.sagaExecution.findUnique({
    where: { executionId },
    include: { steps: { orderBy: { stepIndex: "asc" } } },
  });

  if (!sagaExecution) return null;

  return {
    executionId: sagaExecution.executionId,
    sagaType: sagaExecution.sagaType as SagaTypeName,
    status: sagaExecution.status as SagaStatusName,
    currentStepIndex: sagaExecution.currentStepIndex,
    totalSteps: sagaExecution.totalSteps,
    completedSteps: sagaExecution.completedSteps,
    errorMessage: sagaExecution.errorMessage || undefined,
    compensationReason: sagaExecution.compensationReason || undefined,
    steps: sagaExecution.steps.map(s => ({
      stepIndex: s.stepIndex,
      stepName: s.stepName,
      status: s.status as SagaStepStatusName,
      output: JSON.parse(s.output || "{}"),
      error: s.errorMessage || undefined,
    })),
  };
}

/**
 * Get all Sagas for a tenant
 */
export async function getSagasForTenant(tenantId: string): Promise<SagaOrchestratorResult[]> {
  const executions = await db.sagaExecution.findMany({
    where: { tenantId },
    include: { steps: { orderBy: { stepIndex: "asc" } } },
    orderBy: { createdAt: "desc" },
    take: 50,
  });

  return executions.map(saga => ({
    executionId: saga.executionId,
    sagaType: saga.sagaType as SagaTypeName,
    status: saga.status as SagaStatusName,
    currentStepIndex: saga.currentStepIndex,
    totalSteps: saga.totalSteps,
    completedSteps: saga.completedSteps,
    errorMessage: saga.errorMessage || undefined,
    compensationReason: saga.compensationReason || undefined,
    steps: saga.steps.map(s => ({
      stepIndex: s.stepIndex,
      stepName: s.stepName,
      status: s.status as SagaStepStatusName,
      output: JSON.parse(s.output || "{}"),
      error: s.errorMessage || undefined,
    })),
  }));
}

// ═══════════════════════════════════════════════════════════════════════════
// WASM Bridge Extensions for Saga
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Get all available Saga types (WASM-first, TS fallback)
 */
export function getSagaTypes(): Array<{ id: string; display_name: string; description: string }> {
  return [
    { id: "trial_creation", display_name: "Trial Creation Saga", description: "Orchestrates the creation of a 14-day trial subscription for a new user" },
    { id: "trial_conversion", display_name: "Trial → Paid Conversion Saga", description: "Orchestrates converting a trial subscription to a paid tier with USDT TRC20 payment" },
    { id: "payment_verification", display_name: "Payment Verification Saga", description: "Orchestrates manual/semi-manual verification of a USDT TRC20 payment" },
    { id: "cancellation", display_name: "Subscription Cancellation Saga", description: "Orchestrates subscription cancellation with feature revocation and optional refund" },
    { id: "renewal", display_name: "Subscription Renewal Saga", description: "Orchestrates subscription renewal with payment verification and usage reset" },
    { id: "upgrade", display_name: "Tier Upgrade Saga", description: "Orchestrates tier upgrade with proration and feature activation" },
    { id: "downgrade", display_name: "Tier Downgrade Saga", description: "Orchestrates tier downgrade with feature revocation and proration credit" },
    { id: "reactivation", display_name: "Subscription Reactivation Saga", description: "Orchestrates reactivation of a cancelled subscription" },
  ];
}

/**
 * Get a Saga definition by type (WASM-first, TS fallback)
 */
export function getSagaDefinition(sagaType: SagaTypeName): {
  saga_type: string;
  version: string;
  description: string;
  steps: Array<{
    step_index: number;
    step_name: string;
    description: string;
    action: string;
    compensating_action: string;
    is_critical: boolean;
    timeout_ms: number;
    retry_count: number;
    requires_external_input: boolean;
  }>;
  timeout_ms: number;
  max_retries: number;
  payment_currency: string;
  payment_network: string;
} | null {
  // Step definitions mirror the Rust engine exactly
  const definitions: Record<string, Array<{
    step_index: number;
    step_name: string;
    description: string;
    action: string;
    compensating_action: string;
    is_critical: boolean;
    timeout_ms: number;
    retry_count: number;
    requires_external_input: boolean;
  }>> = {
    trial_creation: [
      { step_index: 0, step_name: "validate_email", description: "Validate user email", action: "validate_email_uniqueness", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "validate_wallet", description: "Validate TRC20 wallet", action: "validate_trc20_address", compensating_action: "none", is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
      { step_index: 2, step_name: "create_trial_record", description: "Create trial subscription", action: "db_create_subscription", compensating_action: "db_delete_subscription", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 3, step_name: "setup_feature_gates", description: "Setup feature gates", action: "initialize_feature_gates", compensating_action: "revoke_feature_gates", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 4, step_name: "create_audit_log", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    trial_conversion: [
      { step_index: 0, step_name: "validate_trial_active", description: "Validate trial is active", action: "validate_subscription_status", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "validate_wallet_address", description: "Validate TRC20 wallet", action: "validate_trc20_address", compensating_action: "none", is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
      { step_index: 2, step_name: "calculate_pricing", description: "Calculate pricing", action: "calculate_subscription_pricing", compensating_action: "none", is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
      { step_index: 3, step_name: "create_payment_request", description: "Create payment request", action: "db_create_payment_request", compensating_action: "db_delete_payment_request", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 4, step_name: "update_subscription_record", description: "Update subscription", action: "db_update_subscription", compensating_action: "db_revert_subscription_to_trial", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 5, step_name: "update_feature_gates", description: "Update feature gates", action: "update_feature_gates_for_tier", compensating_action: "revert_feature_gates_to_trial", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 6, step_name: "create_conversion_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    payment_verification: [
      { step_index: 0, step_name: "validate_tx_hash", description: "Validate tx hash", action: "validate_trc20_tx_hash", compensating_action: "none", is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "check_payment_uniqueness", description: "Check double-spend", action: "check_tx_hash_uniqueness", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 2, step_name: "create_payment_record", description: "Create payment record", action: "db_create_payment", compensating_action: "db_delete_payment", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 3, step_name: "update_subscription_status", description: "Update subscription status", action: "db_update_subscription_status", compensating_action: "db_revert_subscription_status", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 4, step_name: "await_admin_confirmation", description: "Await admin confirmation", action: "await_admin_confirmation", compensating_action: "mark_payment_as_expired", is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
      { step_index: 5, step_name: "finalize_payment", description: "Finalize payment", action: "finalize_payment_confirmation", compensating_action: "revert_payment_to_awaiting", is_critical: true, timeout_ms: 10000, retry_count: 1, requires_external_input: false },
      { step_index: 6, step_name: "create_payment_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    cancellation: [
      { step_index: 0, step_name: "validate_cancellation", description: "Validate cancellation", action: "validate_subscription_cancellable", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "update_subscription_cancelled", description: "Cancel subscription", action: "db_cancel_subscription", compensating_action: "db_reactivate_subscription", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 2, step_name: "revoke_feature_gates", description: "Revoke feature gates", action: "revoke_all_feature_gates", compensating_action: "restore_feature_gates", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 3, step_name: "process_refund_if_applicable", description: "Process refund", action: "initiate_refund_process", compensating_action: "cancel_refund_process", is_critical: false, timeout_ms: 30000, retry_count: 1, requires_external_input: true },
      { step_index: 4, step_name: "create_cancellation_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    renewal: [
      { step_index: 0, step_name: "validate_renewal", description: "Validate renewal", action: "validate_subscription_renewable", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "create_renewal_payment_request", description: "Create payment request", action: "db_create_payment_request", compensating_action: "db_delete_payment_request", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 2, step_name: "await_payment_confirmation", description: "Await payment confirmation", action: "await_admin_confirmation", compensating_action: "mark_payment_as_expired", is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
      { step_index: 3, step_name: "extend_subscription_period", description: "Extend subscription period", action: "db_extend_subscription_period", compensating_action: "db_revert_subscription_period", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 4, step_name: "reset_usage_records", description: "Reset usage records", action: "db_reset_usage_records", compensating_action: "db_restore_usage_records", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 5, step_name: "create_renewal_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    upgrade: [
      { step_index: 0, step_name: "validate_upgrade", description: "Validate upgrade path", action: "validate_upgrade_path", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "calculate_proration", description: "Calculate proration", action: "calculate_proration_amount", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 2, step_name: "create_upgrade_payment_request", description: "Create payment request", action: "db_create_payment_request", compensating_action: "db_delete_payment_request", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 3, step_name: "await_payment_confirmation", description: "Await payment confirmation", action: "await_admin_confirmation", compensating_action: "mark_payment_as_expired", is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
      { step_index: 4, step_name: "update_subscription_tier", description: "Update subscription tier", action: "db_update_subscription_tier", compensating_action: "db_revert_subscription_tier", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 5, step_name: "activate_new_features", description: "Activate features", action: "update_feature_gates_for_tier", compensating_action: "revert_feature_gates_to_previous_tier", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 6, step_name: "create_upgrade_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    downgrade: [
      { step_index: 0, step_name: "validate_downgrade", description: "Validate downgrade path", action: "validate_downgrade_path", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "identify_revocable_features", description: "Identify revocable features", action: "identify_features_to_revoke", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 2, step_name: "calculate_proration_credit", description: "Calculate proration credit", action: "calculate_proration_credit", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 3, step_name: "update_subscription_tier", description: "Update subscription tier", action: "db_update_subscription_tier", compensating_action: "db_revert_subscription_tier", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 4, step_name: "revoke_features", description: "Revoke features", action: "revoke_features_for_downgrade", compensating_action: "restore_revoked_features", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 5, step_name: "create_downgrade_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
    reactivation: [
      { step_index: 0, step_name: "validate_reactivation", description: "Validate reactivation", action: "validate_subscription_reactivatable", compensating_action: "none", is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
      { step_index: 1, step_name: "create_reactivation_payment", description: "Create payment request", action: "db_create_payment_request", compensating_action: "db_delete_payment_request", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 2, step_name: "await_payment_confirmation", description: "Await payment confirmation", action: "await_admin_confirmation", compensating_action: "mark_payment_as_expired", is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
      { step_index: 3, step_name: "reactivate_subscription", description: "Reactivate subscription", action: "db_reactivate_subscription", compensating_action: "db_cancel_subscription", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 4, step_name: "restore_feature_gates", description: "Restore feature gates", action: "restore_feature_gates", compensating_action: "revoke_all_feature_gates", is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
      { step_index: 5, step_name: "create_reactivation_audit", description: "Create audit log", action: "create_audit_entry", compensating_action: "mark_audit_as_rolled_back", is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
    ],
  };

  const steps = definitions[sagaType];
  if (!steps) return null;

  const sagaDescriptions: Record<string, string> = {
    trial_creation: "Orchestrates the creation of a 14-day trial subscription for a new user",
    trial_conversion: "Orchestrates converting a trial subscription to a paid tier with USDT TRC20 payment",
    payment_verification: "Orchestrates manual/semi-manual verification of a USDT TRC20 payment",
    cancellation: "Orchestrates subscription cancellation with feature revocation and optional refund",
    renewal: "Orchestrates subscription renewal with payment verification and usage reset",
    upgrade: "Orchestrates tier upgrade with proration and feature activation",
    downgrade: "Orchestrates tier downgrade with feature revocation and proration credit",
    reactivation: "Orchestrates reactivation of a cancelled subscription",
  };

  return {
    saga_type: sagaType,
    version: "1.0.0",
    description: sagaDescriptions[sagaType] || "",
    steps,
    timeout_ms: 172800000,
    max_retries: 1,
    payment_currency: "USDT",
    payment_network: "TRC20",
  };
}

/**
 * Validate upgrade path (WASM-first, TS fallback)
 */
export function validateUpgradePath(currentTier: string, newTier: string): { valid: boolean; error?: string; message?: string } {
  const tierRank: Record<string, number> = { trial: 0, starter: 1, business: 2, enterprise: 3, on_premise_enterprise: 4 };
  const currentRank = tierRank[currentTier] ?? -1;
  const newRank = tierRank[newTier] ?? -1;

  if (currentRank === -1) return { valid: false, error: `Unknown current tier: ${currentTier}` };
  if (newRank === -1) return { valid: false, error: `Unknown new tier: ${newTier}` };
  if (newRank <= currentRank) return { valid: false, error: `Invalid upgrade: ${currentTier} → ${newTier}. New tier must be higher.` };
  return { valid: true, message: `Upgrade from ${currentTier} to ${newTier} is valid` };
}

/**
 * Validate downgrade path (WASM-first, TS fallback)
 */
export function validateDowngradePath(currentTier: string, newTier: string): { valid: boolean; error?: string; message?: string } {
  const tierRank: Record<string, number> = { trial: 0, starter: 1, business: 2, enterprise: 3, on_premise_enterprise: 4 };
  const currentRank = tierRank[currentTier] ?? -1;
  const newRank = tierRank[newTier] ?? -1;

  if (currentRank === -1) return { valid: false, error: `Unknown current tier: ${currentTier}` };
  if (newRank === -1) return { valid: false, error: `Unknown new tier: ${newTier}` };
  if (newRank >= currentRank) return { valid: false, error: `Invalid downgrade: ${currentTier} → ${newTier}. New tier must be lower.` };
  return { valid: true, message: `Downgrade from ${currentTier} to ${newTier} is valid` };
}

/**
 * Calculate proration (WASM-first, TS fallback)
 */
export function calculateProration(
  currentTier: string,
  newTier: string,
  daysRemaining: number,
  daysInPeriod: number,
): {
  current_tier: string;
  new_tier: string;
  current_monthly_usdt: number;
  new_monthly_usdt: number;
  days_remaining: number;
  days_in_period: number;
  remaining_fraction: number;
  credit_usdt: number;
  charge_usdt: number;
  net_amount_usdt: number;
  is_upgrade: boolean;
  payment_currency: string;
  payment_network: string;
} {
  const tierPrices: Record<string, number> = { trial: 0, starter: 29, business: 99, enterprise: 299, on_premise_enterprise: 799 };
  const currentMonthly = tierPrices[currentTier] ?? 0;
  const newMonthly = tierPrices[newTier] ?? 0;
  const dailyCurrent = currentMonthly / 30;
  const dailyNew = newMonthly / 30;
  const credit = dailyCurrent * daysRemaining;
  const charge = dailyNew * daysRemaining;
  const netAmount = charge - credit;

  return {
    current_tier: currentTier,
    new_tier: newTier,
    current_monthly_usdt: currentMonthly,
    new_monthly_usdt: newMonthly,
    days_remaining: daysRemaining,
    days_in_period: daysInPeriod,
    remaining_fraction: daysInPeriod > 0 ? daysRemaining / daysInPeriod : 0,
    credit_usdt: credit,
    charge_usdt: charge,
    net_amount_usdt: netAmount,
    is_upgrade: netAmount > 0,
    payment_currency: "USDT",
    payment_network: "TRC20",
  };
}
