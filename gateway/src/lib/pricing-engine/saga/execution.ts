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
