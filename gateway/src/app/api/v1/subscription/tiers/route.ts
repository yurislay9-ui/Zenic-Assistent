// ─── Zenic-Agents v3 — Subscription Tiers ──────────────────────────────
// GET /api/v1/subscription/tiers
// Public endpoint — get all available pricing tiers.
// All prices in USDT, TRC20 network only.

import { getPaidTiers, PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

export async function GET() {
  try {
    // No auth required — public endpoint
    // Use getPaidTiers from pricing engine
    const tiers = getPaidTiers();

    return Response.json({
      tiers: tiers.map((tier) => ({
        name: tier.name,
        displayName: tier.display_name,
        monthlyPriceUsdt: tier.monthly_price_usdt,
        annualPriceUsdt: tier.annual_price_usdt,
        setupFeeUsdt: tier.setup_fee_usdt,
        recommendedFor: tier.recommended_for,
        limits: tier.limits,
        paymentCurrency: tier.payment_currency,
        paymentNetwork: tier.payment_network,
      })),
      payment: {
        currency: PAYMENT_CURRENCY,
        network: PAYMENT_NETWORK,
        methods: ["USDT TRC20"],
        note: "All payments are processed via USDT on the TRC20 (Tron) network. No other payment methods are supported.",
      },
      comparison: {
        starter: {
          bestFor: "Small teams starting with automation",
          pricePerDay: (tiers.find((t) => t.name === "starter")?.monthly_price_usdt ?? 29 / 30).toFixed(2),
          highlight: "5 workflows, 200 actions/day",
        },
        business: {
          bestFor: "Growing companies with compliance needs",
          pricePerDay: (tiers.find((t) => t.name === "business")?.monthly_price_usdt ?? 99 / 30).toFixed(2),
          highlight: "25 workflows, custom RBAC, compliance",
        },
        enterprise: {
          bestFor: "Large organizations with strict compliance",
          pricePerDay: (tiers.find((t) => t.name === "enterprise")?.monthly_price_usdt ?? 299 / 30).toFixed(2),
          highlight: "Unlimited workflows, SSO, Z3 solver",
        },
        on_premise_enterprise: {
          bestFor: "Organizations requiring full privacy and on-premise deployment",
          pricePerDay: (tiers.find((t) => t.name === "on_premise_enterprise")?.monthly_price_usdt ?? 799 / 30).toFixed(2),
          highlight: "Air-gap, custom branding, data residency",
        },
      },
      endpoints: {
        signup: "/api/v1/subscription/signup",
        trial: "/api/v1/subscription/trial",
        addons: "/api/v1/subscription/addons",
      },
    });
  } catch (error) {
    console.error("[Subscription Tiers] Error:", error);
    return Response.json(
      { error: "Internal server error retrieving pricing tiers" },
      { status: 500 }
    );
  }
}
