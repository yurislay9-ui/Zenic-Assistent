// ─── Zenic-Agents v3 — Playbooks API: Pricing Calculation ───────────
// POST /api/v1/playbooks/pricing — Calculate pricing for a playbook

import { NextRequest, NextResponse } from "next/server";
import { calculatePricing, formatPricingReport } from "@/lib/playbooks";
import type { PricingTierName } from "@/lib/playbooks";
import { PricingTierName as PricingTierNameEnum } from "@/lib/playbooks";
import { db } from "@/lib/db";

// POST /api/v1/playbooks/pricing
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { playbookId, tier, actionsPerMonth } = body;

    if (!playbookId) {
      return NextResponse.json(
        { error: "playbookId is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    if (!tier) {
      return NextResponse.json(
        { error: "tier is required (starter, business, enterprise, on_premise_enterprise, or trial)", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Validate tier value
    const validTiers: PricingTierName[] = [
      PricingTierNameEnum.STARTER,
      PricingTierNameEnum.BUSINESS,
      PricingTierNameEnum.ENTERPRISE,
      PricingTierNameEnum.ON_PREMISE_ENTERPRISE,
      PricingTierNameEnum.TRIAL,
    ];
    if (!validTiers.includes(tier)) {
      return NextResponse.json(
        { error: `Invalid tier "${tier}". Must be one of: starter, business, enterprise, on_premise_enterprise, trial`, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Load playbook pricing from DB
    const playbook = await db.playbook.findFirst({
      where: { playbookId },
    });

    if (!playbook) {
      return NextResponse.json(
        { error: `Playbook "${playbookId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const pricing = JSON.parse(playbook.pricing);
    const actionsPerMonthNum = actionsPerMonth ? Number(actionsPerMonth) : undefined;

    const pricingCalculation = calculatePricing(pricing, tier, actionsPerMonthNum);
    const formatted = formatPricingReport(pricingCalculation);

    return NextResponse.json({
      pricing: pricingCalculation,
      formatted,
    });
  } catch (error) {
    console.error("[Playbooks Pricing POST]", error);
    return NextResponse.json(
      { error: "Failed to calculate pricing", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
