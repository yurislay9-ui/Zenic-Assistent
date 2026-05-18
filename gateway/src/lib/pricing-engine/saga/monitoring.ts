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
