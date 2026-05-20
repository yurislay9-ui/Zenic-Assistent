// ─── Zenic-Agents v3 — Playbook Pricing Engine: Validator ──────────────
// DB-backed validation functions: estimateCost, getRecommendedTier,
// and the error builder helper.

import type {
  PlaybookPricing,
  PricingTierName,
  PricingTier,
} from "../types";
import { db } from "@/lib/db";
import type { CostEstimate } from "./types";
import { OVERAGE_RATE_PER_ACTION } from "./types";
import { findTier, getIncludedActions, determineTierByActions } from "./_calculator";

/**
 * Estimate total cost for a playbook with custom usage configuration.
 *
 * Loads the playbook from DB, calculates base costs, and includes
 * overage charges if tier limits are exceeded.
 *
 * All values are in USDT, TRC20 network.
 *
 * @param playbookId - Playbook ID to look up in the database
 * @param tier - Selected pricing tier
 * @param config - Custom usage configuration (e.g., { actions_per_month: 5000, workflows: 8 })
 */
export async function estimateCost(
  playbookId: string,
  tier: PricingTierName,
  config: Record<string, number>,
): Promise<CostEstimate> {
  try {
    const playbook = await db.playbook.findFirst({
      where: {
        OR: [
          { playbookId },
          { id: playbookId },
        ],
      },
    });

    if (!playbook) {
      return buildCostEstimateError(
        playbookId,
        tier,
        `Playbook not found: ${playbookId}`,
      );
    }

    const pricing: PlaybookPricing = JSON.parse(playbook.pricing || "{}");
    const tierConfig = findTier(pricing, tier);

    const actionsPerMonth = config.actions_per_month ?? 0;
    const monthlyCost = tierConfig.price_usdt;
    const setupFee = tierConfig.setup_fee_usdt;
    const annualCost = monthlyCost * 10;

    // Calculate included actions from tier limits
    const includedActions = getIncludedActions(tierConfig);
    const overageActions = Math.max(0, actionsPerMonth - includedActions);
    const overageRate = OVERAGE_RATE_PER_ACTION[tier];
    const overageCost = overageActions * overageRate;

    const totalEstimatedMonthly = monthlyCost + overageCost;
    const totalEstimatedAnnual = totalEstimatedMonthly * 10;

    // Build details
    const details: string[] = [
      `Base monthly cost: ${monthlyCost.toFixed(2)} USDT (${tier} tier, TRC20)`,
      `Setup fee: ${setupFee.toFixed(2)} USDT (one-time, TRC20)`,
      `Annual cost with 2-month discount: ${annualCost.toFixed(2)} USDT (TRC20)`,
    ];

    if (actionsPerMonth > 0) {
      const perAction = monthlyCost / actionsPerMonth;
      details.push(`Cost per action: ${perAction.toFixed(4)} USDT`);
    }

    if (overageActions > 0) {
      details.push(
        `Overage: ${overageActions} actions beyond ${includedActions} included ` +
        `at ${overageRate.toFixed(2)} USDT/action = ${overageCost.toFixed(2)} USDT/month (TRC20)`,
      );
    }

    // Check workflow limit
    const workflows = config.workflows ?? 0;
    const maxWorkflows = tierConfig.limits.max_workflows;
    if (typeof maxWorkflows === "number" && workflows > maxWorkflows) {
      details.push(
        `WARNING: ${workflows} workflows exceeds tier limit of ${maxWorkflows}. ` +
        "Consider upgrading to Enterprise or On-Premise for unlimited workflows.",
      );
    }

    // Check team member limit
    const teamMembers = config.team_members ?? 0;
    const maxTeamMembers = tierConfig.limits.team_members;
    if (typeof maxTeamMembers === "number" && teamMembers > maxTeamMembers) {
      details.push(
        `WARNING: ${teamMembers} team members exceeds tier limit of ${maxTeamMembers}. ` +
        "Enterprise and On-Premise tiers offer unlimited team members.",
      );
    }

    if (overageActions === 0 && actionsPerMonth > 0) {
      details.push("Usage within tier limits — no overage charges.");
    }

    return {
      playbookId,
      tier,
      monthlyCost,
      setupFee,
      annualCost,
      overageCost,
      totalEstimatedMonthly,
      totalEstimatedAnnual,
      actionsIncluded: includedActions,
      actionsOverage: overageActions,
      overageRatePerAction: overageRate,
      paymentCurrency: "USDT",
      paymentNetwork: "TRC20",
      details,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return buildCostEstimateError(playbookId, tier, `Database error: ${message}`);
  }
}

/**
 * Get the recommended pricing tier for a playbook based on estimated actions.
 *
 * Logic:
 * - < 500 actions/month → Starter
 * - 500–5000 actions/month → Business
 * - 5000–50000 actions/month → Enterprise
 * - > 50000 actions/month → On-Premise Enterprise
 *
 * Trial tier is never recommended — it's activated separately.
 *
 * @param playbookId - Playbook ID to validate existence
 * @param estimatedActions - Estimated monthly actions
 */
export async function getRecommendedTier(
  playbookId: string,
  estimatedActions: number,
): Promise<PricingTierName> {
  try {
    // Validate playbook exists
    const playbook = await db.playbook.findFirst({
      where: {
        OR: [
          { playbookId },
          { id: playbookId },
        ],
      },
      select: { playbookId: true, pricing: true },
    });

    if (!playbook) {
      // Default recommendation even if playbook not found
      return determineTierByActions(estimatedActions);
    }

    // If playbook has custom pricing with specific recommendations, use those
    const pricing: PlaybookPricing = JSON.parse(playbook.pricing || "{}");
    if (pricing.tiers && pricing.tiers.length > 0) {
      // Check if any tier has explicit action limits that override defaults
      for (const tier of pricing.tiers) {
        const maxActions = tier.limits.max_actions_per_day;
        if (
          typeof maxActions === "number" &&
          estimatedActions <= maxActions * 30
        ) {
          return tier.name;
        }
      }
    }

    return determineTierByActions(estimatedActions);
  } catch {
    // Fallback to default logic on DB error
    return determineTierByActions(estimatedActions);
  }
}

// ─── Internal Helpers ──────────────────────────────────────────────────

/**
 * Build a CostEstimate for error cases.
 */
function buildCostEstimateError(
  playbookId: string,
  tier: PricingTierName,
  errorMessage: string,
): CostEstimate {
  return {
    playbookId,
    tier,
    monthlyCost: 0,
    setupFee: 0,
    annualCost: 0,
    overageCost: 0,
    totalEstimatedMonthly: 0,
    totalEstimatedAnnual: 0,
    actionsIncluded: 0,
    actionsOverage: 0,
    overageRatePerAction: 0,
    paymentCurrency: "USDT",
    paymentNetwork: "TRC20",
    details: [`Error: ${errorMessage}`],
  };
}
