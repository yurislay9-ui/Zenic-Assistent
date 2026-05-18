// ─── WASM Bridge — TypeScript Fallback (Core) ────────────────────────────────
// Mirrors the EXACT same logic as the Rust engine for tier, pricing,
// feature, and usage queries. Used when WASM is unavailable.

import type {
  SubscriptionTierName,
  FeatureName,
  TierInfo,
  TierLimitsInfo,
  AddOnInfo,
  TrialConfigInfo,
  PricingCalc,
  TierComp,
  FeatureCheck,
  TierFeatureInfo,
  UsageCheck,
} from "./types";

import {
  TierName,
  TIER_PRICES_USDT,
  ADDON_PRICES_USDT,
  ADDON_DISPLAY_NAMES,
  ADDON_AVAILABLE_TIERS,
  TRIAL_CONFIG,
  PAYMENT_CURRENCY,
  PAYMENT_NETWORK,
  TIER_LIMITS,
  TIER_DISPLAY_NAMES,
  TIER_RECOMMENDED_FOR,
  FEATURE_TIER_MAP,
  TIER_ORDER,
  PAID_TIER_NAMES,
  ALL_TIER_NAMES,
} from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

export function resolveTierName(tier: string): SubscriptionTierName | null {
  const lower = tier.toLowerCase();
  if (lower === "onpremise" || lower === "on-premise") return TierName.ON_PREMISE_ENTERPRISE;
  const found = ALL_TIER_NAMES.find(t => t === lower);
  return found ?? null;
}

export function tsFeatureAvailable(tierName: SubscriptionTierName, feature: FeatureName): boolean {
  const allowedTiers = FEATURE_TIER_MAP[feature];
  if (!allowedTiers) return false;
  return allowedTiers.includes(tierName);
}

export function tsMinimumTier(feature: FeatureName): string | null {
  const allowedTiers = FEATURE_TIER_MAP[feature];
  if (!allowedTiers || allowedTiers.length === 0) return null;
  // Return the lowest tier in the upgrade path
  for (const tier of TIER_ORDER) {
    if (allowedTiers.includes(tier)) return tier;
  }
  // Check trial separately
  if (allowedTiers.includes(TierName.TRIAL)) return TierName.TRIAL;
  return allowedTiers[0] ?? null;
}

// ═══════════════════════════════════════════════════════════════════════════
// Tier & Pricing Fallbacks
// ═══════════════════════════════════════════════════════════════════════════

export function tsEngineVersion(): string {
  return "3.0.0";
}

export function tsGetAllTiers(): TierInfo[] {
  return ALL_TIER_NAMES.map(name => {
    const prices = TIER_PRICES_USDT[name];
    const limits = TIER_LIMITS[name];
    return {
      name,
      display_name: TIER_DISPLAY_NAMES[name],
      monthly_price_usdt: prices.monthly,
      annual_price_usdt: prices.annual,
      setup_fee_usdt: prices.setup,
      recommended_for: TIER_RECOMMENDED_FOR[name],
      limits,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  });
}

export function tsGetPaidTiers(): TierInfo[] {
  return PAID_TIER_NAMES.map(name => {
    const prices = TIER_PRICES_USDT[name];
    const limits = TIER_LIMITS[name];
    return {
      name,
      display_name: TIER_DISPLAY_NAMES[name],
      monthly_price_usdt: prices.monthly,
      annual_price_usdt: prices.annual,
      setup_fee_usdt: prices.setup,
      recommended_for: TIER_RECOMMENDED_FOR[name],
      limits,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  });
}

export function tsGetAddOns(): AddOnInfo[] {
  return Object.keys(ADDON_PRICES_USDT).map(id => ({
    id,
    display_name: ADDON_DISPLAY_NAMES[id] ?? id,
    monthly_price_usdt: ADDON_PRICES_USDT[id],
    available_for_tiers: ADDON_AVAILABLE_TIERS[id] ?? [],
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  }));
}

export function tsGetTrialConfig(): TrialConfigInfo {
  return TRIAL_CONFIG;
}

export function tsCalculatePricing(tierName: string, addOns?: string[]): PricingCalc {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      tier: tierName,
      monthly_price_usdt: 0,
      annual_price_usdt: 0,
      setup_fee_usdt: 0,
      add_ons_monthly_usdt: 0,
      total_first_month_usdt: 0,
      total_monthly_recurring_usdt: 0,
      total_annual_usdt: 0,
      overage_rate_usdt: 0,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  }

  const prices = TIER_PRICES_USDT[resolved];
  const limits = TIER_LIMITS[resolved];
  const addOnsMonthly = (addOns ?? []).reduce((sum, id) => sum + (ADDON_PRICES_USDT[id] ?? 0), 0);
  const monthly = prices.monthly;
  const annual = prices.annual;
  const setup = prices.setup;

  return {
    tier: resolved,
    monthly_price_usdt: monthly,
    annual_price_usdt: annual,
    setup_fee_usdt: setup,
    add_ons_monthly_usdt: addOnsMonthly,
    total_first_month_usdt: monthly + setup + addOnsMonthly,
    total_monthly_recurring_usdt: monthly + addOnsMonthly,
    total_annual_usdt: annual + setup + (addOnsMonthly * 12),
    overage_rate_usdt: limits.overage_rate_usdt,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

export function tsCompareTiers(estimatedActions: number, addOns?: string[]): TierComp {
  const addOnsMonthly = (addOns ?? []).reduce((sum, id) => sum + (ADDON_PRICES_USDT[id] ?? 0), 0);

  const tiers: PricingCalc[] = PAID_TIER_NAMES.map(name => {
    const prices = TIER_PRICES_USDT[name];
    const limits = TIER_LIMITS[name];
    const monthly = prices.monthly;
    return {
      tier: name,
      monthly_price_usdt: monthly,
      annual_price_usdt: prices.annual,
      setup_fee_usdt: prices.setup,
      add_ons_monthly_usdt: addOnsMonthly,
      total_first_month_usdt: monthly + prices.setup + addOnsMonthly,
      total_monthly_recurring_usdt: monthly + addOnsMonthly,
      total_annual_usdt: prices.annual + prices.setup + (addOnsMonthly * 12),
      overage_rate_usdt: limits.overage_rate_usdt,
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  });

  let recommended: string;
  let reason: string;

  if (estimatedActions < 500) {
    recommended = TierName.STARTER;
    reason = `Con ${estimatedActions} acciones/mes, Starter ofrece el mejor valor.`;
  } else if (estimatedActions <= 5000) {
    recommended = TierName.BUSINESS;
    reason = `Con ${estimatedActions} acciones/mes, Business es la elección óptima.`;
  } else if (estimatedActions <= 50000) {
    recommended = TierName.ENTERPRISE;
    reason = `Con ${estimatedActions} acciones/mes, Enterprise maximiza el ROI.`;
  } else {
    recommended = TierName.ON_PREMISE_ENTERPRISE;
    reason = `Con ${estimatedActions} acciones/mes, On-Premise Enterprise es la solución.`;
  }

  return {
    tiers,
    recommended_tier: recommended,
    recommendation_reason: reason,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// Feature & Usage Fallbacks
// ═══════════════════════════════════════════════════════════════════════════

export function tsCheckFeature(tierName: string, featureName: string): FeatureCheck {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      feature: featureName,
      tier: tierName,
      available: false,
      minimum_tier: null,
      denial_reason: `Unknown tier: ${tierName}`,
    };
  }

  const feature = featureName as FeatureName;
  const allowedTiers = FEATURE_TIER_MAP[feature];
  if (!allowedTiers) {
    return {
      feature: featureName,
      tier: tierName,
      available: false,
      minimum_tier: null,
      denial_reason: `Unknown feature: ${featureName}`,
    };
  }

  const available = tsFeatureAvailable(resolved, feature);
  const minTier = tsMinimumTier(feature);

  return {
    feature: featureName,
    tier: tierName,
    available,
    minimum_tier: minTier,
    denial_reason: available
      ? null
      : `Feature '${featureName}' requires upgrade from '${TIER_DISPLAY_NAMES[resolved]}'`,
  };
}

export function tsGetTierFeatures(tierName: string): TierFeatureInfo {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      tier: tierName,
      display_name: tierName,
      features: [],
      payment_currency: PAYMENT_CURRENCY,
      payment_network: PAYMENT_NETWORK,
    };
  }

  const featureNames = Object.keys(FEATURE_TIER_MAP) as FeatureName[];
  const features = featureNames.map(name => {
    const available = tsFeatureAvailable(resolved, name);
    const minTier = tsMinimumTier(name);
    return {
      feature: name,
      available,
      minimum_tier: minTier,
    };
  });

  return {
    tier: tierName,
    display_name: TIER_DISPLAY_NAMES[resolved],
    features,
    payment_currency: PAYMENT_CURRENCY,
    payment_network: PAYMENT_NETWORK,
  };
}

export function tsCheckUsage(tierName: string, resource: string, currentUsage: number): UsageCheck {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return {
      resource,
      allowed: false,
      current_usage: currentUsage,
      max_allowed: 0,
      remaining: 0,
      overage_charge_usdt: 0,
      minimum_tier: null,
      feature_available: false,
      denial_reason: `Unknown tier: ${tierName}`,
    };
  }

  const limits = TIER_LIMITS[resolved];
  const resourceMap: Record<string, { max: number; overageRate: number }> = {
    workflows: { max: limits.max_workflows, overageRate: 0 },
    actions_per_day: { max: limits.max_actions_per_day, overageRate: limits.overage_rate_usdt },
    policies: { max: limits.max_policies, overageRate: 0 },
    team_members: { max: limits.max_team_members, overageRate: 0 },
    mcp_tools: { max: limits.max_mcp_tools, overageRate: 0 },
    approval_requests_per_day: { max: limits.max_approval_requests_per_day, overageRate: limits.overage_rate_usdt },
    playbooks: { max: limits.max_playbooks, overageRate: 0 },
    namespaces: { max: limits.max_namespaces, overageRate: 0 },
    simulations_per_month: { max: limits.max_simulations_per_month, overageRate: 0 },
  };

  const entry = resourceMap[resource];
  if (!entry) {
    return {
      resource,
      allowed: false,
      current_usage: currentUsage,
      max_allowed: 0,
      remaining: 0,
      overage_charge_usdt: 0,
      minimum_tier: null,
      feature_available: false,
      denial_reason: `Unknown resource: ${resource}`,
    };
  }

  const max = entry.max;
  const overageRate = entry.overageRate;
  const allowed = max === 0 || currentUsage <= max;
  const remaining = max === 0 ? 0 : Math.max(0, max - currentUsage);
  const overage = max > 0 && currentUsage > max ? (currentUsage - max) * overageRate : 0;
  const denialReason = !allowed && max > 0
    ? `Usage ${currentUsage} exceeds limit ${max} for '${resource}' on ${TIER_DISPLAY_NAMES[resolved]} tier. Upgrade required.`
    : null;

  return {
    resource,
    allowed,
    current_usage: currentUsage,
    max_allowed: max,
    remaining,
    overage_charge_usdt: overage,
    minimum_tier: null,
    feature_available: allowed,
    denial_reason: denialReason,
  };
}

export function tsGetTierLimits(tierName: string): TierLimitsInfo {
  const resolved = resolveTierName(tierName);
  if (!resolved) {
    return TIER_LIMITS[TierName.STARTER];
  }
  return TIER_LIMITS[resolved];
}
