// ─── Zenic-Agents v3 — Subscription Cancel ─────────────────────────────
// POST /api/v1/subscription/cancel
// Cancel a subscription. All payments were USDT TRC20.

import { db } from "@/lib/db";
import { PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

interface CancelBody {
  tenantId: string;
  reason?: string;
}

export async function POST(request: Request) {
  try {
    const body: CancelBody = await request.json();
    const { tenantId, reason } = body;

    // Validate required fields
    if (!tenantId) {
      return Response.json(
        { error: "Missing required field: tenantId" },
        { status: 400 }
      );
    }

    // Look up subscription
    const existing = await db.subscription.findUnique({
      where: { tenantId },
    });

    if (!existing) {
      return Response.json(
        {
          error: "No subscription found for this tenant",
          tenantId,
        },
        { status: 404 }
      );
    }

    // Check if already cancelled
    if (existing.status === "cancelled") {
      return Response.json(
        {
          error: "Subscription is already cancelled",
          tenantId,
          subscriptionId: existing.subscriptionId,
          cancelledAt: existing.cancelledAt?.toISOString(),
          cancellationReason: existing.cancellationReason,
        },
        { status: 400 }
      );
    }

    // Set status to "cancelled", record cancellation details
    const now = new Date();
    const cancellationReason = reason ?? "User requested cancellation";

    const updated = await db.subscription.update({
      where: { tenantId },
      data: {
        status: "cancelled",
        autoRenew: false,
        cancelledAt: now,
        cancellationReason,
        updatedAt: now,
      },
    });

    // Return cancellation confirmation
    return Response.json({
      confirmation: {
        subscriptionId: updated.subscriptionId,
        tenantId: updated.tenantId,
        previousStatus: existing.status,
        currentStatus: updated.status,
        cancelledAt: updated.cancelledAt?.toISOString(),
        cancellationReason: updated.cancellationReason,
        tier: updated.tier,
        paymentMethod: updated.paymentMethod,
        paymentCurrency: PAYMENT_CURRENCY,
        paymentNetwork: PAYMENT_NETWORK,
        message: existing.status === "trial"
          ? "Trial subscription cancelled successfully. No payment was required."
          : `Subscription cancelled. Your access will continue until the end of the current billing period (${updated.currentPeriodEnd.toISOString()}). No further USDT TRC20 charges will be made.`,
        billingPeriodEnd: updated.currentPeriodEnd.toISOString(),
        reactivateEndpoint: "/api/v1/subscription/signup",
      },
    });
  } catch (error) {
    console.error("[Subscription Cancel] Error:", error);
    return Response.json(
      { error: "Internal server error cancelling subscription" },
      { status: 500 }
    );
  }
}
