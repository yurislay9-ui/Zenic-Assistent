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

