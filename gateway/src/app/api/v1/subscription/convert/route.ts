// ─── Zenic-Agents v3 — Subscription Convert Trial ──────────────────────
// POST /api/v1/subscription/convert
// Convert a trial subscription to a paid subscription. USDT TRC20 only.
// After conversion, subscription status is "pending_payment" (admin must confirm payment).

import { db } from "@/lib/db";
import {
  validateTrc20Address,
  convertTrialToPaid,
  PAID_TIER_NAMES,
  PAYMENT_CURRENCY,
  PAYMENT_NETWORK,
} from "@/lib/pricing-engine";

interface ConvertBody {
  tenantId: string;
  tier: string;
  billingWalletAddress: string;
  addOns?: string[];
}

export async function POST(request: Request) {
  try {
    const body: ConvertBody = await request.json();
    const { tenantId, tier, billingWalletAddress, addOns } = body;

    // Validate required fields
    if (!tenantId || !tier || !billingWalletAddress) {
      return Response.json(
        { error: "Missing required fields: tenantId, tier, billingWalletAddress" },
        { status: 400 }
      );
    }

    // Validate tier is a paid tier (not trial)
    if (!PAID_TIER_NAMES.includes(tier as typeof PAID_TIER_NAMES[number])) {
      return Response.json(
        {
          error: `Invalid tier '${tier}'. Must be a paid tier: ${PAID_TIER_NAMES.join(", ")}`,
        },
        { status: 400 }
      );
    }

    // Validate wallet address
    const walletValidation = validateTrc20Address(billingWalletAddress);
    if (!walletValidation.valid) {
      return Response.json(
        {
          error: "Invalid billing wallet address",
          details: walletValidation,
          hint: "TRC20 address must start with 'T' and be 34 characters alphanumeric",
        },
        { status: 400 }
      );
    }

    // Look up existing subscription
    const existing = await db.subscription.findUnique({
      where: { tenantId },
    });

    if (!existing) {
      return Response.json(
        {
          error: "No subscription found for this tenant",
          tenantId,
          hint: "Use /api/v1/subscription/trial to start a 14-day free trial first",
        },
        { status: 404 }
      );
    }

    // Validate it's in trial status
    if (existing.status !== "trial") {
      return Response.json(
        {
          error: "Subscription is not in trial status",
          tenantId,
          currentStatus: existing.status,
          hint: "Only trial subscriptions can be converted. Use /api/v1/subscription/signup for new subscriptions.",
        },
        { status: 400 }
      );
    }

    // Convert to paid using pricing engine
    const conversionResult = convertTrialToPaid(tenantId, tier, billingWalletAddress);

    // Update DB record — status is "pending_payment" (admin must confirm payment)
    const now = new Date();
    const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

    const updated = await db.subscription.update({
      where: { tenantId },
      data: {
        tier: conversionResult.subscription.tier,
        status: "pending_payment",
        billingWalletAddress,
        addOns: JSON.stringify(addOns ?? conversionResult.subscription.add_ons),
        currentPeriodEnd: periodEnd,
        trialEndsAt: existing.trialEndsAt, // Keep trial end date for reference
        trialCompletedAt: now,
        autoRenew: true,
        paymentMethod: "usdt_trc20",
        updatedAt: now,
      },
    });

    // Return new subscription + payment info
    return Response.json({
      subscription: {
        id: updated.id,
        subscriptionId: updated.subscriptionId,
        tenantId: updated.tenantId,
        tier: updated.tier,
        status: updated.status,
        paymentMethod: updated.paymentMethod,
        billingWalletAddress: updated.billingWalletAddress,
        addOns: JSON.parse(updated.addOns),
        startedAt: updated.startedAt.toISOString(),
        currentPeriodEnd: updated.currentPeriodEnd.toISOString(),
        trialEndsAt: updated.trialEndsAt?.toISOString() ?? null,
        trialCompletedAt: updated.trialCompletedAt?.toISOString() ?? null,
        autoRenew: updated.autoRenew,
      },
      paymentInfo: {
        amountRequiredUsdt: conversionResult.payment_required,
        breakdown: conversionResult.breakdown,
        paymentCurrency: conversionResult.payment_currency,
        paymentNetwork: conversionResult.payment_network,
        status: "pending",
        message: conversionResult.message,
        verifyEndpoint: "/api/v1/subscription/payment/verify",
      },
      conversion: {
        from: "trial",
        to: conversionResult.subscription.tier,
        convertedAt: now.toISOString(),
        trialCompletedAt: now.toISOString(),
      },
      nextSteps: {
        step1: "POST /api/v1/subscription/payment/verify → Submit USDT TRC20 tx_hash",
        step2: "POST /api/v1/subscription/payment/confirm → Admin confirms payment manually",
        note: "Subscription will become 'active' only after admin confirms payment. Current status: pending_payment.",
      },
    });
  } catch (error) {
    console.error("[Subscription Convert] Error:", error);
    return Response.json(
      { error: "Internal server error converting trial subscription" },
      { status: 500 }
    );
  }
}
