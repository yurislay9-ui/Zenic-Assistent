// ─── Zenic-Agents v3 — Subscription Trial ───────────────────────────────
// POST /api/v1/subscription/trial
// Start a 14-day trial subscription. USDT TRC20 only.

import { db } from "@/lib/db";
import {
  createTrialSubscription,
  PAYMENT_CURRENCY,
  PAYMENT_NETWORK,
} from "@/lib/pricing-engine";

interface TrialBody {
  tenantId: string;
  email: string;
}

export async function POST(request: Request) {
  try {
    const body: TrialBody = await request.json();
    const { tenantId, email } = body;

    // Validate required fields
    if (!tenantId || !email) {
      return Response.json(
        { error: "Missing required fields: tenantId, email" },
        { status: 400 }
      );
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return Response.json(
        { error: "Invalid email address format" },
        { status: 400 }
      );
    }

    // Check if tenant already has a subscription (deny if yes)
    const existing = await db.subscription.findUnique({
      where: { tenantId },
    });

    if (existing) {
      return Response.json(
        {
          error: "Tenant already has a subscription",
          tenantId,
          existingSubscriptionId: existing.subscriptionId,
          existingStatus: existing.status,
          hint: existing.status === "trial"
            ? "Your trial is already active. Use /api/v1/subscription/convert to upgrade."
            : "You already have an active subscription.",
        },
        { status: 400 }
      );
    }

    // Create trial subscription using pricing engine
    const trialResult = createTrialSubscription(tenantId, email);

    // Store in DB with status "trial", trialEndsAt = now + 14 days
    const now = new Date();
    const trialEndsAt = new Date(now.getTime() + trialResult.trial_config.duration_days * 24 * 60 * 60 * 1000);
    const periodEnd = new Date(trialEndsAt);

    const subscription = await db.subscription.create({
      data: {
        subscriptionId: trialResult.subscription.id,
        tenantId,
        tier: "trial",
        status: "trial",
        paymentMethod: "usdt_trc20",
        billingWalletAddress: "",
        addOns: JSON.stringify(trialResult.subscription.add_ons),
        startedAt: now,
        currentPeriodEnd: periodEnd,
        trialEndsAt,
        autoRenew: false,
      },
    });

    // Return trial details
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
          autoRenew: subscription.autoRenew,
        },
        trialConfig: trialResult.trial_config,
        message: trialResult.message,
        paymentRequired: trialResult.payment_required,
        paymentCurrency: PAYMENT_CURRENCY,
        paymentNetwork: PAYMENT_NETWORK,
        daysRemaining: trialResult.trial_config.duration_days,
        convertEndpoint: "/api/v1/subscription/convert",
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("[Subscription Trial] Error:", error);
    return Response.json(
      { error: "Internal server error creating trial subscription" },
      { status: 500 }
    );
  }
}
