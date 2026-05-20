// ─── Zenic-Agents v3 — Playbook Pricing Engine: Calculator ──────────────
// Pure pricing calculation functions: calculatePricing, compareTiers,
// formatPricingReport, findTier, and internal helpers.

import type {
  PlaybookPricing,
  PricingTierName,
  PricingCalculation,
  PricingTier,
} from "../types";
import {
  PricingTierName as TierName,
  DEFAULT_STARTER_TIER,
  DEFAULT_BUSINESS_TIER,
  DEFAULT_ENTERPRISE_TIER,
  DEFAULT_ON_PREMISE_TIER,
  DEFAULT_TRIAL_TIER,
} from "../types";
import type { TierComparison } from "./types";
import {
  SAVINGS_PER_ACTION,
  DEFAULT_MONTHLY_ACTIONS,
} from "./types";

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
export function getIncludedActions(tier: PricingTier): number {
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
export function determineTierByActions(actions: number): PricingTierName {
  if (actions < 500) return TierName.STARTER;
  if (actions <= 5000) return TierName.BUSINESS;
  if (actions <= 50000) return TierName.ENTERPRISE;
  return TierName.ON_PREMISE_ENTERPRISE;
}
