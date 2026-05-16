// ─── Zenic-Agents v3 — Subscription Usage ───────────────────────────────
// GET /api/v1/subscription/usage?tenantId=xxx&period=current
// Get usage stats for tenant vs tier limits. USDT TRC20 for overage charges.

import { db } from "@/lib/db";
import { getTierLimits, checkUsage, PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tenantId = searchParams.get("tenantId");
    const period = searchParams.get("period") ?? "current";

    if (!tenantId) {
      return Response.json(
        { error: "Missing required query parameter: tenantId" },
        { status: 400 }
      );
    }

    // Look up subscription
    const subscription = await db.subscription.findUnique({
      where: { tenantId },
    });

    if (!subscription) {
      return Response.json(
        {
          error: "No subscription found for this tenant",
          tenantId,
          hint: "Use /api/v1/subscription/trial to start a trial",
        },
        { status: 404 }
      );
    }

    // Get tier limits from pricing engine
    const tierLimits = getTierLimits(subscription.tier);

    // Determine period range
    const now = new Date();
    let periodStart: Date;
    let periodEnd: Date;

    if (period === "current") {
      periodStart = subscription.currentPeriodEnd.getTime() - 30 * 24 * 60 * 60 * 1000 > subscription.startedAt.getTime()
        ? new Date(subscription.currentPeriodEnd.getTime() - 30 * 24 * 60 * 60 * 1000)
        : subscription.startedAt;
      periodEnd = subscription.currentPeriodEnd;
    } else {
      // Custom period parsing could be added here
      periodStart = subscription.startedAt;
      periodEnd = now;
    }

    // Look up usage records for the period
    const usageRecords = await db.usageRecord.findMany({
      where: {
        subscriptionDbId: subscription.id,
        tenantId,
        periodStart: { gte: periodStart },
        periodEnd: { lte: periodEnd },
      },
      orderBy: { resource: "asc" },
    });

    // Build usage vs limits for all resources
    const resources = [
      "workflows",
      "actions_per_day",
      "policies",
      "team_members",
      "mcp_tools",
      "approval_requests_per_day",
      "playbooks",
      "namespaces",
      "simulations_per_month",
    ] as const;

    const usageStats = resources.map((resource) => {
      // Find matching usage record
      const record = usageRecords.find((r) => r.resource === resource);
      const currentUsage = record?.usageCount ?? 0;

      // Use pricing engine to check usage
      const usageCheck = checkUsage(subscription.tier, resource, currentUsage);

      return {
        resource,
        currentUsage,
        maxAllowed: usageCheck.max_allowed,
        remaining: usageCheck.remaining,
        allowed: usageCheck.allowed,
        overageCount: record?.overageCount ?? 0,
        overageChargeUsdt: usageCheck.overage_charge_usdt,
        unlimited: usageCheck.max_allowed === 0,
        denialReason: usageCheck.denial_reason,
      };
    });

    // Calculate totals
    const totalOverageChargeUsdt = usageStats.reduce(
      (sum, s) => sum + s.overageChargeUsdt,
      0
    );

    return Response.json({
      tenantId,
      subscription: {
        subscriptionId: subscription.subscriptionId,
        tier: subscription.tier,
        status: subscription.status,
      },
      period: {
        type: period,
        start: periodStart.toISOString(),
        end: periodEnd.toISOString(),
      },
      tierLimits,
      usage: usageStats,
      summary: {
        totalResources: resources.length,
        resourcesAtLimit: usageStats.filter((s) => !s.allowed && !s.unlimited).length,
        unlimitedResources: usageStats.filter((s) => s.unlimited).length,
        totalOverageChargeUsdt,
        overageCurrency: PAYMENT_CURRENCY,
        overageNetwork: PAYMENT_NETWORK,
      },
      paymentCurrency: PAYMENT_CURRENCY,
      paymentNetwork: PAYMENT_NETWORK,
    });
  } catch (error) {
    console.error("[Subscription Usage] Error:", error);
    return Response.json(
      { error: "Internal server error retrieving usage stats" },
      { status: 500 }
    );
  }
}
