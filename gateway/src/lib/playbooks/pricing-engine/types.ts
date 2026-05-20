// ─── Zenic-Agents v3 — Playbook Pricing Engine: Types ────────────────────
// Shared types and constants for the pricing-engine module.

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

// Re-export from parent types so consumers don't break
export type {
  PlaybookPricing,
  PricingTierName,
  PricingCalculation,
  PricingTier,
};
export {
  PricingTierName as TierName,
  DEFAULT_STARTER_TIER,
  DEFAULT_BUSINESS_TIER,
  DEFAULT_ENTERPRISE_TIER,
  DEFAULT_ON_PREMISE_TIER,
  DEFAULT_TRIAL_TIER,
} from "../types";

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
export const SAVINGS_PER_ACTION: Record<PricingTierName, number> = {
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
export const OVERAGE_RATE_PER_ACTION: Record<PricingTierName, number> = {
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
export const DEFAULT_MONTHLY_ACTIONS: Record<PricingTierName, number> = {
  [TierName.STARTER]: 6000,              // 200/day * 30
  [TierName.BUSINESS]: 60000,            // 2000/day * 30
  [TierName.ENTERPRISE]: Number.MAX_SAFE_INTEGER,  // unlimited
  [TierName.ON_PREMISE_ENTERPRISE]: Number.MAX_SAFE_INTEGER, // unlimited
  [TierName.TRIAL]: 60000,               // Same as Business
};
