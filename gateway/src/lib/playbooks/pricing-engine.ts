// ─── Zenic-Agents v3 — Playbook Pricing Engine ─────────────────────────
// Phase 4 (Updated): Factory pattern for pricing calculations across 5 tiers.
//
// Calculates monthly, annual, per-action costs and break-even analysis.
// Compares tiers side-by-side and recommends the best fit per usage.
// All payments are USDT TRC20 only.
//
// Tiers: Starter ($29) / Business ($99) / Enterprise ($299) /
//        On-Premise Enterprise ($799 + $2000 setup) / Trial (14 days free)
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
  DEFAULT_BUSINESS_TIER,
  DEFAULT_ENTERPRISE_TIER,
  DEFAULT_ON_PREMISE_TIER,
  DEFAULT_TRIAL_TIER,
} from "./types";
import { db } from "@/lib/db";

// ─── Exported Types ────────────────────────────────────────────────────

/** Side-by-side tier comparison with recommendation */
export interface TierComparison {
  /** Playbook ID if comparison was loaded from DB */
  playbookId?: string;
  /** Currency code (always USDT) */
  currency: string;
  /** Payment network (always TRC20) */
  network: string;
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
  /** Base monthly cost from the tier price (USDT) */
  monthlyCost: number;
  /** One-time setup fee (USDT) */
  setupFee: number;
  /** Annual cost (monthly * 10 with 2-month discount) (USDT) */
  annualCost: number;
  /** Overage charges for exceeding tier limits (USDT) */
  overageCost: number;
  /** Total estimated monthly cost including overages (USDT) */
  totalEstimatedMonthly: number;
  /** Total estimated annual cost including overages (USDT) */
  totalEstimatedAnnual: number;
  /** Number of actions included in the base tier */
  actionsIncluded: number;
  /** Number of actions beyond the included amount */
  actionsOverage: number;
  /** Overage rate per action beyond the limit (USDT) */
  overageRatePerAction: number;
  /** Payment currency — always USDT */
  paymentCurrency: string;
  /** Payment network — always TRC20 */
  paymentNetwork: string;
  /** Human-readable details explaining the estimate */
  details: string[];
}

// ─── Internal Constants ────────────────────────────────────────────────

/**
 * Estimated savings per automated action by tier (USDT).
 * Higher tiers have more capabilities → greater per-action savings.
 */
const SAVINGS_PER_ACTION: Record<PricingTierName, number> = {
  [TierName.STARTER]: 2,
  [TierName.BUSINESS]: 5,
  [TierName.ENTERPRISE]: 10,
  [TierName.ON_PREMISE_ENTERPRISE]: 15,
  [TierName.TRIAL]: 5, // Same as Business during trial
};

/**
 * Overage rate per action when tier limits are exceeded (USDT).
 * Charged per action beyond the tier's max_actions_per_day * 30.
 */
const OVERAGE_RATE_PER_ACTION: Record<PricingTierName, number> = {
  [TierName.STARTER]: 0.15,
  [TierName.BUSINESS]: 0.10,
  [TierName.ENTERPRISE]: 0.0,
  [TierName.ON_PREMISE_ENTERPRISE]: 0.0,
  [TierName.TRIAL]: 0.10, // Same as Business during trial
};

/**
 * Default monthly action limits inferred from tier limits.
 * These are used when the tier limits specify max_actions_per_day.
 */
const DEFAULT_MONTHLY_ACTIONS: Record<PricingTierName, number> = {
  [TierName.STARTER]: 6000,              // 200/day * 30
  [TierName.BUSINESS]: 60000,            // 2000/day * 30
  [TierName.ENTERPRISE]: Number.MAX_SAFE_INTEGER,  // unlimited
  [TierName.ON_PREMISE_ENTERPRISE]: Number.MAX_SAFE_INTEGER, // unlimited
  [TierName.TRIAL]: 60000,               // Same as Business
};

// ─── Factory Functions ─────────────────────────────────────────────────

/**
 * Calculate pricing for a specific tier.
 *
 * - monthly_cost_usdt = tier.price_usdt
 * - annual_cost_usdt = monthly_cost * 10 (2 months free for annual billing)
 * - setup_fee_usdt = tier.setup_fee_usdt
 * - per_action_cost = monthly_cost / actions (if provided)
 * - break_even_actions = Math.ceil((monthly_cost + setup_fee_usdt) / savings_per_action)
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
  const monthly_cost_usdt = tierConfig.price_usdt;
  const setup_fee_usdt = tierConfig.setup_fee_usdt;
  const annual_cost_usdt = monthly_cost_usdt * 10; // 2 months free for annual
  const per_action_cost =
    actionsPerMonth && actionsPerMonth > 0
      ? monthly_cost_usdt / actionsPerMonth
      : 0;

  const savingsPerAction = SAVINGS_PER_ACTION[tier];
  const break_even_actions = savingsPerAction > 0
    ? Math.ceil((monthly_cost_usdt + setup_fee_usdt) / savingsPerAction)
    : 0;

  return {
    selected_tier: tier,
    monthly_cost_usdt,
    annual_cost_usdt,
    setup_fee_usdt,
    per_action_cost,
    break_even_actions,
    payment_currency: "USDT",
    payment_network: "TRC20",
  };
}

/**
 * Compare all four paid pricing tiers side-by-side.
 *
 * Highlights the recommended tier based on usage patterns:
 * - < 500 actions/month → Starter
 * - 500–5000 actions/month → Business
 * - 5000–50000 actions/month → Enterprise
 * - > 50000 actions/month → On-Premise Enterprise
 *
 * Trial tier is excluded from comparison (it's a temporary tier).
 *
 * @param pricing - Playbook pricing configuration
 * @param estimatedActions - Estimated monthly actions for recommendation
 */
export function compareTiers(
  pricing: PlaybookPricing,
  estimatedActions: number = 5000,
): TierComparison {
  // Filter out trial tier for comparison
  const paidTiers = pricing.tiers.filter((t) => t.name !== TierName.TRIAL);

  const tierCalculations = paidTiers.map((tier) => {
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

  if (estimatedActions < 500) {
    recommendedTier = TierName.STARTER;
    recommendationReason =
      `With ${estimatedActions} actions/month, Starter provides the best value. ` +
      "Includes 5 workflows and basic compliance checks for small teams. Payment via USDT TRC20.";
  } else if (estimatedActions <= 5000) {
    recommendedTier = TierName.BUSINESS;
    recommendationReason =
      `With ${estimatedActions} actions/month, Business is the optimal choice. ` +
      "Includes 25 workflows, advanced compliance & audit, API access, and HITL approval workflow. Payment via USDT TRC20.";
  } else if (estimatedActions <= 50000) {
    recommendedTier = TierName.ENTERPRISE;
    recommendationReason =
      `With ${estimatedActions} actions/month, Enterprise delivers maximum ROI. ` +
      "Unlimited workflows, full compliance suite, dedicated support, SSO/RBAC, and Z3 constraint solver. Payment via USDT TRC20.";
  } else {
    recommendedTier = TierName.ON_PREMISE_ENTERPRISE;
    recommendationReason =
      `With ${estimatedActions} actions/month, On-Premise Enterprise is the right choice. ` +
      "Everything in Enterprise plus on-premise deployment, air-gap capability, custom branding, and data residency control. Payment via USDT TRC20.";
  }

  // Mark the recommended tier
  for (const tc of tierCalculations) {
    tc.recommended = tc.tier.name === recommendedTier;
  }

  return {
    currency: pricing.currency,
    network: pricing.network ?? "TRC20",
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

/**
 * Format a pricing calculation as a human-readable report.
 */
export function formatPricingReport(calc: PricingCalculation): string {
  const lines: string[] = [
    "┌─────────────────────────────────────────────┐",
    "│       Playbook Pricing Summary               │",
    "│       Payment: USDT (TRC20 Network)          │",
    "├─────────────────────────────────────────────┤",
    `│  Tier:            ${calc.selected_tier.padEnd(26)}│`,
    `│  Monthly Cost:    ${calc.monthly_cost_usdt.toFixed(2)} USDT`.padEnd(47) + "│",
    `│  Annual Cost:     ${calc.annual_cost_usdt.toFixed(2)} USDT`.padEnd(47) + "│",
    `│  (2 months free with annual billing)         │`,
  ];

  if (calc.setup_fee_usdt > 0) {
    lines.push(
      `│  Setup Fee:       ${calc.setup_fee_usdt.toFixed(2)} USDT (one-time)`.padEnd(47) + "│",
    );
  }

  if (calc.per_action_cost > 0) {
    lines.push(
      `│  Per Action:      ${calc.per_action_cost.toFixed(4)} USDT`.padEnd(47) + "│",
    );
  }

  if (calc.break_even_actions > 0) {
    lines.push(
      `│  Break-Even:      ${String(calc.break_even_actions).padEnd(26)}│`,
      `│  (actions needed to cover monthly cost)      │`,
    );
  }

  lines.push(
    `│  Network:         TRC20`.padEnd(47) + "│",
    "└─────────────────────────────────────────────┘",
  );

  return lines.join("\n");
}

/**
 * Find a specific tier by name. Returns the matching tier from the pricing
 * configuration or falls back to the default tier constants.
 */
export function findTier(pricing: PlaybookPricing, tierName: PricingTierName): PricingTier {
  const tier = pricing.tiers?.find((t) => t.name === tierName);
  if (tier) {
    return tier;
  }
  // Return default tier from types.ts constants if not found
  const defaults: Record<PricingTierName, PricingTier> = {
    [TierName.STARTER]: DEFAULT_STARTER_TIER,
    [TierName.BUSINESS]: DEFAULT_BUSINESS_TIER,
    [TierName.ENTERPRISE]: DEFAULT_ENTERPRISE_TIER,
    [TierName.ON_PREMISE_ENTERPRISE]: DEFAULT_ON_PREMISE_TIER,
    [TierName.TRIAL]: DEFAULT_TRIAL_TIER,
  };
  return defaults[tierName];
}

// ─── Internal Helpers ──────────────────────────────────────────────────

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
  return DEFAULT_MONTHLY_ACTIONS[tier.name] ?? 6000;
}

/**
 * Determine tier by estimated monthly actions (simple heuristic).
 *
 * - < 500 → Starter
 * - 500–5000 → Business
 * - 5000–50000 → Enterprise
 * - > 50000 → On-Premise Enterprise
 *
 * Trial is never auto-recommended.
 */
function determineTierByActions(actions: number): PricingTierName {
  if (actions < 500) return TierName.STARTER;
  if (actions <= 5000) return TierName.BUSINESS;
  if (actions <= 50000) return TierName.ENTERPRISE;
  return TierName.ON_PREMISE_ENTERPRISE;
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
