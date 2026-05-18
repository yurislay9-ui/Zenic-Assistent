// ─── Zenic-Agents v3 — YAML Loader Compilers: ROI & Pricing ────────────
// Split from _compilers.ts — ROI baseline/projected/calculation and pricing tier compilation

import type {
  PlaybookRoiConfig,
  RoiBaseline,
  RoiProjected,
  RoiCalculation,
  PlaybookPricing,
  PricingTier,
  PricingTierName,
} from "../types";
import { PricingTierName as PricingTierNameEnum } from "../types";
import { PlaybookValidationError } from "./_types";
import type { PlaybookYamlLoaderConfig } from "./_types";
import {
  VALID_TIER_NAMES,
} from "./_types";

// ─── ROI Config Compilation ───────────────────────────────────────────

export function compileRoiConfig(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookRoiConfig {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi must be an object", "roi");
  }

  const obj = raw as Record<string, unknown>;

  if (!obj.baseline || typeof obj.baseline !== "object") {
    throw new PlaybookValidationError("roi.baseline is required and must be an object", "roi.baseline");
  }
  const baseline = compileRoiBaseline(obj.baseline, config);

  if (!obj.projected || typeof obj.projected !== "object") {
    throw new PlaybookValidationError("roi.projected is required and must be an object", "roi.projected");
  }
  const projected = compileRoiProjected(obj.projected, config);

  const assumptions = Array.isArray(obj.assumptions)
    ? obj.assumptions.map(String)
    : [];

  const calculated = computeRoiCalculation(baseline, projected, 0);

  return { baseline, projected, assumptions, calculated };
}

export function compileRoiBaseline(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): RoiBaseline {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi.baseline must be an object", "roi.baseline");
  }

  const obj = raw as Record<string, unknown>;
  const prefix = "roi.baseline";

  const requiredNumbers: Array<keyof RoiBaseline> = [
    "manual_time_per_action_min", "error_rate_pct", "actions_per_month",
    "cost_per_error_usd", "violations_per_year", "penalty_per_violation_usd",
  ];

  for (const field of requiredNumbers) {
    if (config.strictValidation && typeof obj[field] !== "number") {
      throw new PlaybookValidationError(
        `${prefix}.${field} is required and must be a number`,
        `${prefix}.${field}`,
        obj[field],
      );
    }
  }

  return {
    manual_time_per_action_min: typeof obj.manual_time_per_action_min === "number" ? obj.manual_time_per_action_min : 30,
    error_rate_pct: typeof obj.error_rate_pct === "number" ? obj.error_rate_pct : 5,
    actions_per_month: typeof obj.actions_per_month === "number" ? obj.actions_per_month : 1000,
    cost_per_error_usd: typeof obj.cost_per_error_usd === "number" ? obj.cost_per_error_usd : 50,
    violations_per_year: typeof obj.violations_per_year === "number" ? obj.violations_per_year : 12,
    penalty_per_violation_usd: typeof obj.penalty_per_violation_usd === "number" ? obj.penalty_per_violation_usd : 5000,
  };
}

export function compileRoiProjected(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): RoiProjected {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi.projected must be an object", "roi.projected");
  }

  const obj = raw as Record<string, unknown>;
  const prefix = "roi.projected";

  const requiredNumbers: Array<keyof RoiProjected> = [
    "automated_time_per_action_min", "reduced_error_rate_pct",
    "compliance_score_target", "automation_rate_pct",
  ];

  for (const field of requiredNumbers) {
    if (config.strictValidation && typeof obj[field] !== "number") {
      throw new PlaybookValidationError(
        `${prefix}.${field} is required and must be a number`,
        `${prefix}.${field}`,
        obj[field],
      );
    }
  }

  return {
    automated_time_per_action_min: typeof obj.automated_time_per_action_min === "number" ? obj.automated_time_per_action_min : 5,
    reduced_error_rate_pct: typeof obj.reduced_error_rate_pct === "number" ? obj.reduced_error_rate_pct : 0.5,
    compliance_score_target: typeof obj.compliance_score_target === "number" ? obj.compliance_score_target : 95,
    automation_rate_pct: typeof obj.automation_rate_pct === "number" ? obj.automation_rate_pct : 80,
  };
}

export function computeRoiCalculation(
  baseline: RoiBaseline,
  projected: RoiProjected,
  monthlyCostUsd: number,
): RoiCalculation {
  const workingHoursPerMonth = 160;
  const hourlyCostUsd = 50;

  const timeSavedPerActionMin = baseline.manual_time_per_action_min - projected.automated_time_per_action_min;
  const automatedActionsPerMonth = baseline.actions_per_month * (projected.automation_rate_pct / 100);
  const time_saved_hours_month = (timeSavedPerActionMin * automatedActionsPerMonth) / 60;

  const originalErrorsPerMonth = baseline.actions_per_month * (baseline.error_rate_pct / 100);
  const newErrorsPerMonth = automatedActionsPerMonth * (projected.reduced_error_rate_pct / 100);
  const errors_avoided_month = originalErrorsPerMonth - newErrorsPerMonth;

  const violationReductionPct = Math.max(0, projected.compliance_score_target - (100 - baseline.error_rate_pct * 5));
  const compliance_risk_reduction_usd = baseline.violations_per_year * baseline.penalty_per_violation_usd * (violationReductionPct / 100);

  const timeSavingsAnnual = time_saved_hours_month * hourlyCostUsd * 12;
  const errorSavingsAnnual = errors_avoided_month * baseline.cost_per_error_usd * 12;
  const totalSavingsAnnual = timeSavingsAnnual + errorSavingsAnnual + compliance_risk_reduction_usd;
  const totalCostAnnual = monthlyCostUsd * 12;
  const net_roi_usd = totalSavingsAnnual - totalCostAnnual;

  const roi_percentage = totalCostAnnual > 0 ? (net_roi_usd / totalCostAnnual) * 100 : 0;

  const monthlySavings = totalSavingsAnnual / 12;
  const payback_months = monthlySavings > 0 ? Math.ceil(totalCostAnnual / monthlySavings) : 999;

  return {
    time_saved_hours_month: Math.round(time_saved_hours_month * 100) / 100,
    errors_avoided_month: Math.round(errors_avoided_month * 100) / 100,
    compliance_risk_reduction_usd: Math.round(compliance_risk_reduction_usd * 100) / 100,
    net_roi_usd: Math.round(net_roi_usd * 100) / 100,
    roi_percentage: Math.round(roi_percentage * 100) / 100,
    payback_months,
  };
}

// ─── Pricing Compilation ──────────────────────────────────────────────

export function compilePricing(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookPricing {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("pricing must be an object", "pricing");
  }

  const obj = raw as Record<string, unknown>;

  let tiers: PricingTier[];

  if (Array.isArray(obj.tiers)) {
    tiers = obj.tiers.map((t: unknown, i: number) =>
      compilePricingTier(t, i, config),
    );
  } else {
    const nestedTiers: PricingTier[] = [];
    const tierKeys = [PricingTierNameEnum.STARTER, PricingTierNameEnum.BUSINESS, PricingTierNameEnum.ENTERPRISE, PricingTierNameEnum.ON_PREMISE_ENTERPRISE, PricingTierNameEnum.TRIAL];

    for (const key of tierKeys) {
      const tierData = obj[key];
      if (tierData && typeof tierData === "object") {
        const tierObj = { ...(tierData as Record<string, unknown>), name: key };
        nestedTiers.push(compilePricingTier(tierObj, nestedTiers.length, config));
      }
    }

    tiers = nestedTiers;
  }

  const tierNames = tiers.map((t) => t.name);
  if (!tierNames.includes(PricingTierNameEnum.STARTER as string) || !tierNames.includes(PricingTierNameEnum.BUSINESS as string)) {
    throw new PlaybookValidationError(
      "pricing.tiers must include both 'starter' and 'business' tiers",
      "pricing.tiers",
    );
  }

  return {
    currency: typeof obj.currency === "string" ? obj.currency : "USDT",
    network: typeof obj.network === "string" ? obj.network : "TRC20",
    tiers,
  };
}

export function compilePricingTier(
  raw: unknown,
  index: number,
  config: PlaybookYamlLoaderConfig,
): PricingTier {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`pricing.tiers[${index}] must be an object`, `pricing.tiers[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `pricing.tiers[${index}]`;

  const name = typeof obj.name === "string" ? obj.name : "";
  if (config.strictValidation && !VALID_TIER_NAMES.has(name)) {
    throw new PlaybookValidationError(
      `${prefix}.name must be one of: ${[...VALID_TIER_NAMES].join(", ")}`,
      `${prefix}.name`,
      name,
    );
  }

  return {
    name: name as PricingTier["name"],
    price_usdt: typeof obj.price_usdt === "number" ? obj.price_usdt : (typeof obj.price_usd === "number" ? obj.price_usd : 0),
    setup_fee_usdt: typeof obj.setup_fee_usdt === "number" ? obj.setup_fee_usdt : 0,
    features: Array.isArray(obj.features) ? obj.features.map(String) : [],
    limits: obj.limits && typeof obj.limits === "object"
      ? obj.limits as Record<string, number | "unlimited">
      : {},
    recommended_for: typeof obj.recommended_for === "string" ? obj.recommended_for : "",
    payment_currency: typeof obj.payment_currency === "string" ? obj.payment_currency : "USDT",
    payment_network: typeof obj.payment_network === "string" ? obj.payment_network : "TRC20",
  };
}
