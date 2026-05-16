// ─── Zenic-Agents v3 — Subscription GET ─────────────────────────────────
// GET /api/v1/subscription?tenantId=xxx
// Look up subscription for tenant. If not found, return 404 with trial offer.
// All monetary values in USDT, TRC20 network.

import { db } from "@/lib/db";
import { getTierLimits, getTrialConfig, PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tenantId = searchParams.get("tenantId");

    if (!tenantId) {
      return Response.json(
        { error: "Missing required query parameter: tenantId" },
        { status: 400 }
      );
    }

    // Look up subscription from DB by tenantId
    const subscription = await db.subscription.findUnique({
      where: { tenantId },
      include: {
        payments: {
          orderBy: { createdAt: "desc" },
          take: 5,
        },
        usageRecords: {
          where: {
            periodStart: { lte: new Date() },
            periodEnd: { gte: new Date() },
          },
        },
      },
    });

    if (!subscription) {
      // Return 404 with trial offer
      const trialConfig = getTrialConfig();
      return Response.json(
        {
          error: "No subscription found for this tenant",
          tenantId,
          trialOffer: {
            available: true,
            durationDays: trialConfig.duration_days,
            grantedTier: trialConfig.granted_tier,
            maxTrialsPerEmail: trialConfig.max_trials_per_email,
            autoConvert: trialConfig.auto_convert,
            message: `Start a ${trialConfig.duration_days}-day free trial with full ${trialConfig.granted_tier} tier access. No credit card required.`,
            paymentCurrency: PAYMENT_CURRENCY,
            paymentNetwork: PAYMENT_NETWORK,
            signupEndpoint: "/api/v1/subscription/trial",
          },
        },
        { status: 404 }
      );
    }

    // Return full subscription details with tier limits
    const tierLimits = getTierLimits(subscription.tier);

    return Response.json({
      subscription: {
        id: subscription.id,
        subscriptionId: subscription.subscriptionId,
        tenantId: subscription.tenantId,
        tier: subscription.tier,
        status: subscription.status,
        paymentMethod: subscription.paymentMethod,
        billingWalletAddress: subscription.billingWalletAddress,
        addOns: JSON.parse(subscription.addOns),
        startedAt: subscription.startedAt.toISOString(),
        currentPeriodEnd: subscription.currentPeriodEnd.toISOString(),
        trialEndsAt: subscription.trialEndsAt?.toISOString() ?? null,
        autoRenew: subscription.autoRenew,
        lastPaymentTxHash: subscription.lastPaymentTxHash,
        lastPaymentAmountUsdt: subscription.lastPaymentAmount,
        lastPaymentAt: subscription.lastPaymentAt?.toISOString() ?? null,
        cancelledAt: subscription.cancelledAt?.toISOString() ?? null,
        cancellationReason: subscription.cancellationReason,
        createdAt: subscription.createdAt.toISOString(),
        updatedAt: subscription.updatedAt.toISOString(),
      },
      tierLimits,
      recentPayments: subscription.payments.map((p) => ({
        paymentId: p.paymentId,
        amountUsdt: p.amountUsdt,
        txHash: p.txHash,
        network: p.network,
        status: p.status,
        paidAt: p.paidAt?.toISOString() ?? null,
        confirmedAt: p.confirmedAt?.toISOString() ?? null,
      })),
      currentUsage: subscription.usageRecords.map((u) => ({
        resource: u.resource,
        usageCount: u.usageCount,
        limitValue: u.limitValue,
        overageCount: u.overageCount,
        overageChargeUsdt: u.overageChargeUsdt,
        periodStart: u.periodStart.toISOString(),
        periodEnd: u.periodEnd.toISOString(),
      })),
      paymentCurrency: PAYMENT_CURRENCY,
      paymentNetwork: PAYMENT_NETWORK,
    });
  } catch (error) {
    console.error("[Subscription GET] Error:", error);
    return Response.json(
      { error: "Internal server error retrieving subscription" },
      { status: 500 }
    );
  }
}
