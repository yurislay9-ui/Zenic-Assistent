// ─── Zenic-Agents v3 — Subscription Add-ons ────────────────────────────
// GET /api/v1/subscription/addons?tier=xxx
// Get available add-ons with USDT TRC20 prices.

import { getAddOns, PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tier = searchParams.get("tier") ?? undefined;

    // Use getAddOns from pricing engine
    const allAddOns = getAddOns();

    // Filter by tier if provided
    const addOns = tier
      ? allAddOns.filter((addon) => addon.available_for_tiers.includes(tier))
      : allAddOns;

    return Response.json({
      addOns: addOns.map((addon) => ({
        id: addon.id,
        displayName: addon.display_name,
        monthlyPriceUsdt: addon.monthly_price_usdt,
        availableForTiers: addon.available_for_tiers,
        paymentCurrency: addon.payment_currency,
        paymentNetwork: addon.payment_network,
      })),
      filter: tier ?? null,
      totalAvailable: addOns.length,
      payment: {
        currency: PAYMENT_CURRENCY,
        network: PAYMENT_NETWORK,
        note: "Add-on prices are monthly, billed in USDT via TRC20 network. Add-ons are added to your base subscription price.",
      },
      availableAddOnIds: addOns.map((a) => a.id),
      endpoints: {
        signup: "/api/v1/subscription/signup",
        tiers: "/api/v1/subscription/tiers",
      },
    });
  } catch (error) {
    console.error("[Subscription Addons] Error:", error);
    return Response.json(
      { error: "Internal server error retrieving add-ons" },
      { status: 500 }
    );
  }
}
