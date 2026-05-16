// ─── Zenic-Agents v3 — Subscription Signup ──────────────────────────────
// POST /api/v1/subscription/signup
// Sign up for a paid subscription. TRIAL-FIRST: All users must complete a 14-day trial first.
// All payments USDT TRC20 only. Manual admin confirmation required.

import { db } from "@/lib/db";
import {
  validateTrc20Address,
  calculatePricing,
  PAID_TIER_NAMES,
  PAYMENT_CURRENCY,
  PAYMENT_NETWORK,
} from "@/lib/pricing-engine";

interface SignupBody {
  tenantId: string;
  tier: string;
  billingWalletAddress: string;
  addOns?: string[];
}

export async function POST(request: Request) {
  try {
    const body: SignupBody = await request.json();
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
          hint: "Use /api/v1/subscription/trial to start a trial instead",
        },
        { status: 400 }
      );
    }

    // Validate wallet address using TRC20 validation
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

    // ── TRIAL-FIRST ENFORCEMENT ──────────────────────────────────────
    // All users MUST start with a 14-day free trial before signing up for a paid plan.
    const existing = await db.subscription.findUnique({
      where: { tenantId },
    });

    if (!existing) {
      // No subscription at all — must start with trial
      return Response.json(
        {
          error: "All users must start with a 14-day free trial. Use /api/v1/subscription/trial first.",
          tenantId,
          flow: {
            step1: "POST /api/v1/subscription/trial → Get 14-day Business trial",
            step2: "After trial ends, POST /api/v1/subscription/convert → Convert to paid plan",
            step3: "POST /api/v1/subscription/payment/verify → Provide USDT TRC20 tx_hash",
            step4: "POST /api/v1/subscription/payment/confirm → Admin confirms payment",
          },
        },
        { status: 400 }
      );
    }

    // If a trial subscription exists and is still active, cannot sign up directly
    if (existing.status === "trial") {
      const now = new Date();
      const trialStillActive = existing.trialEndsAt && existing.trialEndsAt > now;

      if (trialStillActive) {
        return Response.json(
          {
            error: "Your trial is still active. Use /api/v1/subscription/convert to convert to a paid plan when ready.",
            tenantId,
            currentStatus: existing.status,
            trialEndsAt: existing.trialEndsAt?.toISOString(),
            hint: "Use /api/v1/subscription/convert to convert your active trial to a paid plan",
          },
          { status: 400 }
        );
      }
    }

    // If subscription exists but is not in an ended-trial state, reject
    // Allow only if: trial expired, or status is "expired"
    const trialExpired = existing.status === "trial" && existing.trialEndsAt && existing.trialEndsAt <= new Date();
    const statusExpired = existing.status === "expired";

    if (!trialExpired && !statusExpired) {
      return Response.json(
        {
          error: "Tenant already has an active subscription",
          tenantId,
          existingSubscriptionId: existing.subscriptionId,
          existingStatus: existing.status,
          hint: existing.status === "trial"
            ? "Use /api/v1/subscription/convert to convert your trial to a paid plan"
            : "Use /api/v1/subscription/cancel to cancel your current subscription first",
        },
        { status: 400 }
      );
    }

    // ── TRIAL COMPLETED — Allow paid signup ──────────────────────────
    // Calculate pricing
    const pricing = calculatePricing(tier, addOns);

    // Create subscription in DB with status "pending_payment" (requires manual admin confirmation)
    const now = new Date();
    const periodEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    const subscriptionId = `sub_${tenantId.slice(0, 8)}_${Date.now().toString(36)}`;

    const subscription = await db.subscription.update({
      where: { tenantId },
      data: {
        subscriptionId,
        tier,
        status: "pending_payment",
        paymentMethod: "usdt_trc20",
        billingWalletAddress,
        addOns: JSON.stringify(addOns ?? []),
        currentPeriodEnd: periodEnd,
        trialEndsAt: existing.trialEndsAt, // Keep trial end date for reference
        trialCompletedAt: now,
        autoRenew: true,
        updatedAt: now,
      },
    });

    // Return subscription + first payment details
    return Response.json(
      {
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
          trialCompletedAt: subscription.trialCompletedAt?.toISOString() ?? null,
          autoRenew: subscription.autoRenew,
        },
        firstPayment: {
          amountUsdt: pricing.total_first_month_usdt,
          breakdown: {
            monthlyUsdt: pricing.monthly_price_usdt,
            setupFeeUsdt: pricing.setup_fee_usdt,
            addOnsMonthlyUsdt: pricing.add_ons_monthly_usdt,
            firstPaymentUsdt: pricing.total_first_month_usdt,
          },
          paymentCurrency: PAYMENT_CURRENCY,
          paymentNetwork: PAYMENT_NETWORK,
          status: "pending",
          message: `Payment of ${pricing.total_first_month_usdt} USDT required via TRC20 network. Use /api/v1/subscription/payment/verify to submit your payment. Admin will manually confirm.`,
        },
        pricing,
        nextSteps: {
          step1: "POST /api/v1/subscription/payment/verify → Submit USDT TRC20 tx_hash",
          step2: "POST /api/v1/subscription/payment/confirm → Admin confirms payment manually",
          note: "Subscription will become 'active' only after admin confirms payment.",
        },
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("[Subscription Signup] Error:", error);
    return Response.json(
      { error: "Internal server error creating subscription" },
      { status: 500 }
    );
  }
}
