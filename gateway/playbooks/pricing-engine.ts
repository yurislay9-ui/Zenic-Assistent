// ─── Zenic-Agents v3 — Playbook Pricing Engine ─────────────────────────
// Phase 4: Factory pattern for pricing calculations across all tiers.
//
// Calculates monthly, annual, per-action costs and break-even analysis.
// Compares tiers side-by-side and recommends the best fit per usage.
//
// Design Patterns:
//   - Factory: creates PricingCalculation and TierComparison objects
//   - Strategy: tier-based savings estimation for break-even

import type {
  PlaybookPricing,
  PricingTierName,
  PricingCalculation,
  PricingTier,
} from "./types";
import {
  PricingTierName as TierName,
  DEFAULT_STARTER_TIER,
  DEFAULT_PRO_TIER,
  DEFAULT_ENTERPRISE_TIER,
} from "./types";
import { db } from "@/lib/db";

// ─── Exported Types ────────────────────────────────────────────────────

/** Side-by-side tier comparison with recommendation */
export interface TierComparison {
  /** Playbook ID if comparison was loaded from DB */
  playbookId?: string;
  /** Currency code */
  currency: string;
  /** Per-tier comparison details */
  tiers: Array<{
    tier: PricingTier;
    calculation: PricingCalculation;
    recommended: boolean;
  }>;
  /** The recommended tier name */
  recommendedTier: PricingTierName;
  /** Human-readable reason for the recommendation */
  recommendationReason: string;
}

/** Custom usage-based cost estimate with overage calculations */
export interface CostEstimate {
  /** Playbook ID */
  playbookId: string;
  /** Selected tier */
  tier: PricingTierName;
  /** Base monthly cost from the tier price */
  monthlyCost: number;
  /** Annual cost (monthly * 10 with 2-month discount) */
  annualCost: number;
  /** Overage charges for exceeding tier limits */
  overageCost: number;
  /** Total estimated monthly cost including overages */
  totalEstimatedMonthly: number;
  /** Total estimated annual cost including overages */
  totalEstimatedAnnual: number;
  /** Number of actions included in the base tier */
  actionsIncluded: number;
  /** Number of actions beyond the included amount */
  actionsOverage: number;
  /** Overage rate per action beyond the limit */
  overageRatePerAction: number;
  /** Human-readable details explaining the estimate */
  details: string[];
}

// ─── Internal Constants ────────────────────────────────────────────────

/**
 * Estimated savings per automated action by tier.
 * Higher tiers have more capabilities → greater per-action savings.
 */
const SAVINGS_PER_ACTION: Record<PricingTierName, number> = {
  [TierName.STARTER]: 4,
  [TierName.PRO]: 6,
  [TierName.ENTERPRISE]: 10,
};

/**
 * Overage rate per action when tier limits are exceeded.
 * Charged per action beyond the tier's max_actions_per_day * 30.
 */
const OVERAGE_RATE_PER_ACTION: Record<PricingTierName, number> = {
  [TierName.STARTER]: 0.5,
  [TierName.PRO]: 0.35,
  [TierName.ENTERPRISE]: 0.25,
};

/**
 * Default monthly action limits inferred from tier limits.
 * These are used when the tier limits specify max_actions_per_day.
 */
const DEFAULT_MONTHLY_ACTIONS: Record<PricingTierName, number> = {
  [TierName.STARTER]: 3000,   // 100/day * 30
  [TierName.PRO]: 30000,      // 1000/day * 30
  [TierName.ENTERPRISE]: 300000, // effectively unlimited
};

// ─── Factory Functions ─────────────────────────────────────────────────

/**
 * Calculate pricing for a specific tier.
 *
 * - monthly_cost = tier.price_usd
 * - annual_cost = monthly_cost * 10 (2 months free for annual billing)
 * - per_action_cost = monthly_cost / actions (if provided)
 * - break_even_actions = Math.ceil(monthly_cost / savings_per_action)
 *
 * @param pricing - Playbook pricing configuration with all tiers
 * @param tier - Which tier to calculate for
 * @param actionsPerMonth - Optional custom actions/month for per-action cost
 */
export function calculatePricing(
  pricing: PlaybookPricing,
  tier: PricingTierName,
  actionsPerMonth?: number,
): PricingCalculation {
  const tierConfig = findTier(pricing, tier);
  const monthly_cost = tierConfig.price_usd;
  const annual_cost = monthly_cost * 10; // 2 months free for annual
  const per_action_cost =
    actionsPerMonth && actionsPerMonth > 0
      ? monthly_cost / actionsPerMonth
      : 0;

  const savingsPerAction = SAVINGS_PER_ACTION[tier];
  const break_even_actions = savingsPerAction > 0
    ? Math.ceil(monthly_cost / savingsPerAction)
    : 0;

  return {
    selected_tier: tier,
    monthly_cost,
    annual_cost,
    per_action_cost,
    break_even_actions,
  };
}

/**
 * Compare all three pricing tiers side-by-side.
 *
 * Highlights the recommended tier based on usage patterns:
 * - < 1000 actions/month → starter
 * - 1000–10000 actions/month → pro
 * - > 10000 actions/month → enterprise
 *
 * @param pricing - Playbook pricing configuration
 * @param estimatedActions - Estimated monthly actions for recommendation
 */
export function compareTiers(
  pricing: PlaybookPricing,
  estimatedActions: number = 5000,
): TierComparison {
  const tierCalculations = pricing.tiers.map((tier) => {
    const calculation = calculatePricing(pricing, tier.name, estimatedActions);
    return {
      tier,
      calculation,
      recommended: false, // set below
    };
  });

  // Determine recommended tier based on estimated actions
  let recommendedTier: PricingTierName;
  let recommendationReason: string;

  if (estimatedActions < 1000) {
    recommendedTier = TierName.STARTER;
    recommendationReason =
      `With ${estimatedActions} actions/month, Starter provides the best value. ` +
      "Includes 5 workflows and basic compliance checks for small teams.";
  } else if (estimatedActions <= 10000) {
    recommendedTier = TierName.PRO;
    recommendationReason =
      `With ${estimatedActions} actions/month, Pro is the optimal choice. ` +
      "Includes 25 workflows, advanced compliance & audit, and API access for growing businesses.";
  } else {
    recommendedTier = TierName.ENTERPRISE;
    recommendationReason =
      `With ${estimatedActions} actions/month, Enterprise delivers maximum ROI. ` +
      "Unlimited workflows, full compliance suite, dedicated support, and SSO/RBAC integration.";
  }

  // Mark the recommended tier
  for (const tc of tierCalculations) {
    tc.recommended = tc.tier.name === recommendedTier;
  }

  return {
    currency: pricing.currency,
    tiers: tierCalculations,
    recommendedTier,
    recommendationReason,
  };
}

/**
 * Estimate total cost for a playbook with custom usage configuration.
 *
 * Loads the playbook from DB, calculates base costs, and includes
 * overage charges if tier limits are exceeded.
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
    const monthlyCost = tierConfig.price_usd;
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
      `Base monthly cost: $${monthlyCost.toFixed(2)} (${tier} tier)`,
      `Annual cost with 2-month discount: $${annualCost.toFixed(2)}`,
    ];

    if (actionsPerMonth > 0) {
      const perAction = monthlyCost / actionsPerMonth;
      details.push(`Cost per action: $${perAction.toFixed(4)}`);
    }

    if (overageActions > 0) {
      details.push(
        `Overage: ${overageActions} actions beyond ${includedActions} included ` +
        `at $${overageRate.toFixed(2)}/action = $${overageCost.toFixed(2)}/month`,
      );
    }

    // Check workflow limit
    const workflows = config.workflows ?? 0;
    const maxWorkflows = tierConfig.limits.max_workflows;
    if (typeof maxWorkflows === "number" && workflows > maxWorkflows) {
      details.push(
        `WARNING: ${workflows} workflows exceeds tier limit of ${maxWorkflows}. ` +
        "Consider upgrading to Enterprise for unlimited workflows.",
      );
    }

    // Check team member limit
    const teamMembers = config.team_members ?? 0;
    const maxTeamMembers = tierConfig.limits.team_members;
    if (typeof maxTeamMembers === "number" && teamMembers > maxTeamMembers) {
      details.push(
        `WARNING: ${teamMembers} team members exceeds tier limit of ${maxTeamMembers}. ` +
        "Enterprise tier offers unlimited team members.",
      );
    }

    if (overageActions === 0 && actionsPerMonth > 0) {
      details.push("Usage within tier limits — no overage charges.");
    }

    return {
      playbookId,
      tier,
      monthlyCost,
      annualCost,
      overageCost,
      totalEstimatedMonthly,
      totalEstimatedAnnual,
      actionsIncluded: includedActions,
      actionsOverage: overageActions,
      overageRatePerAction: overageRate,
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
 * - < 1000 actions/month → starter
 * - 1000–10000 actions/month → pro
 * - > 10000 actions/month → enterprise
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
    if (pricing.tiers && pricing.tiers.length === 3) {
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

/**
 * Format a pricing calculation as a human-readable report.
 */
export function formatPricingReport(calc: PricingCalculation): string {
  const lines: string[] = [
    "┌─────────────────────────────────────────────┐",
    "│       Playbook Pricing Summary               │",
    "├─────────────────────────────────────────────┤",
    `│  Tier:            ${calc.selected_tier.padEnd(26)}│`,
    `│  Monthly Cost:    $${calc.monthly_cost.toFixed(2).padEnd(25)}│`,
    `│  Annual Cost:     $${calc.annual_cost.toFixed(2).padEnd(25)}│`,
    `│  (2 months free with annual billing)         │`,
  ];

  if (calc.per_action_cost > 0) {
    lines.push(
      `│  Per Action:      $${calc.per_action_cost.toFixed(4).padEnd(25)}│`,
    );
  }

  if (calc.break_even_actions > 0) {
    lines.push(
      `│  Break-Even:      ${String(calc.break_even_actions).padEnd(26)}│`,
      `│  (actions needed to cover monthly cost)      │`,
    );
  }

  lines.push("└─────────────────────────────────────────────┘");

  return lines.join("\n");
}

// ─── Internal Helpers ──────────────────────────────────────────────────

/**
 * Find a specific tier within a PlaybookPricing configuration.
 */
function findTier(pricing: PlaybookPricing, tierName: PricingTierName): PricingTier {
  const tier = pricing.tiers.find((t) => t.name === tierName);
  if (!tier) {
    // Return default tier from types.ts constants if not found
    const defaults: Record<PricingTierName, PricingTier> = {
      [TierName.STARTER]: DEFAULT_STARTER_TIER,
      [TierName.PRO]: DEFAULT_PRO_TIER,
      [TierName.ENTERPRISE]: DEFAULT_ENTERPRISE_TIER,
    };
    return defaults[tierName];
  }
  return tier;
}

/**
 * Get the number of monthly actions included in a tier.
 */
function getIncludedActions(tier: PricingTier): number {
  const maxPerDay = tier.limits.max_actions_per_day;
  if (maxPerDay === "unlimited") {
    return Number.MAX_SAFE_INTEGER;
  }
  if (typeof maxPerDay === "number") {
    return maxPerDay * 30;
  }
  // Fallback to default estimates
  return DEFAULT_MONTHLY_ACTIONS[tier.name] ?? 3000;
}

/**
 * Determine tier by estimated monthly actions (simple heuristic).
 */
function determineTierByActions(actions: number): PricingTierName {
  if (actions < 1000) return TierName.STARTER;
  if (actions <= 10000) return TierName.PRO;
  return TierName.ENTERPRISE;
}

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
    annualCost: 0,
    overageCost: 0,
    totalEstimatedMonthly: 0,
    totalEstimatedAnnual: 0,
    actionsIncluded: 0,
    actionsOverage: 0,
    overageRatePerAction: 0,
    details: [`Error: ${errorMessage}`],
  };
}
