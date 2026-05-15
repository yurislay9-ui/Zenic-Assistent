// ─── Zenic-Agents v3 — ROI Calculator (Strategy Pattern) ─────────────
// Phase 4: Industry-specific ROI formulas with month-by-month projections.
//
// Strategy pattern: each industry maps to a formula type that applies
// different multipliers and factors to the base ROI calculation.
//
// Formulas:
//   STANDARD       — time savings + error reduction + compliance risk
//   FINANCIAL      — adds regulatory fine avoidance factor
//   HEALTHCARE     — adds patient safety value factor
//   MANUFACTURING  — adds production downtime reduction factor
//   COMPLIANCE_HEAVY — weights compliance risk reduction higher

import { db } from "@/lib/db";
import type {
  PlaybookRoiConfig,
  RoiCalculation,
  RoiFormulaType,
  Industry,
  RoiBaseline,
  RoiProjected,
} from "./types";
import { INDUSTRY_ROI_FORMULA_MAP, RoiFormulaType as RoiFormulaTypeEnum } from "./types";

// ─── Defaults ────────────────────────────────────────────────────────

/** Default hourly cost of an employee in USD */
const DEFAULT_HOURLY_RATE_USD = 50;

/** Default monthly platform cost (Pro tier) in USD */
const DEFAULT_MONTHLY_PLATFORM_COST_USD = 799;

/** Default annual platform cost in USD */
const DEFAULT_ANNUAL_PLATFORM_COST_USD = DEFAULT_MONTHLY_PLATFORM_COST_USD * 12;

// ─── Industry-Specific Multipliers ──────────────────────────────────

/**
 * Strategy parameters per formula type.
 * Each strategy adjusts the base calculation with industry-specific factors.
 */
interface RoiStrategyParams {
  /** Multiplier applied to compliance risk reduction */
  complianceWeight: number;
  /** Additional savings factor (added to total_savings_month) */
  industryFactor: number;
  /** Description of the industry factor */
  industryFactorLabel: string;
}

const ROI_STRATEGIES: Record<RoiFormulaType, RoiStrategyParams> = {
  /** Standard: no additional industry factors */
  [RoiFormulaTypeEnum.STANDARD]: {
    complianceWeight: 1.0,
    industryFactor: 0,
    industryFactorLabel: "none",
  },
  /** Financial: regulatory fine avoidance boosts compliance value by 50% */
  [RoiFormulaTypeEnum.FINANCIAL]: {
    complianceWeight: 1.5,
    industryFactor: 0.10, // 10% additional savings from fraud prevention
    industryFactorLabel: "regulatory_fine_avoidance",
  },
  /** Healthcare: patient safety value adds 15% to total savings */
  [RoiFormulaTypeEnum.HEALTHCARE]: {
    complianceWeight: 1.2,
    industryFactor: 0.15, // 15% additional savings from patient safety
    industryFactorLabel: "patient_safety_value",
  },
  /** Manufacturing: production downtime reduction adds 20% to total savings */
  [RoiFormulaTypeEnum.MANUFACTURING]: {
    complianceWeight: 1.0,
    industryFactor: 0.20, // 20% additional savings from downtime reduction
    industryFactorLabel: "production_downtime_reduction",
  },
  /** Compliance-heavy: compliance risk weighted 80% higher */
  [RoiFormulaTypeEnum.COMPLIANCE_HEAVY]: {
    complianceWeight: 1.8,
    industryFactor: 0.05, // 5% additional savings from audit efficiency
    industryFactorLabel: "audit_efficiency_gain",
  },
};

// ─── RoiProjection Type ─────────────────────────────────────────────

/** Month-by-month cumulative ROI projection */
export interface RoiProjection {
  /** Month number (1-based) */
  month: number;
  /** Cumulative savings in USD up to this month */
  cumulativeSavingsUsd: number;
  /** Cumulative platform cost in USD up to this month */
  cumulativeCostUsd: number;
  /** Cumulative net ROI in USD (savings - cost) */
  cumulativeNetRoiUsd: number;
  /** Savings for this specific month in USD */
  monthlySavingsUsd: number;
  /** Platform cost for this specific month in USD */
  monthlyCostUsd: number;
}

// ─── Core Calculation ───────────────────────────────────────────────

/**
 * Calculate ROI from a playbook ROI configuration.
 * Uses the strategy pattern to apply industry-specific formula adjustments.
 *
 * Standard formula:
 *   time_saved_hours_month = ((baseline.manual_time_per_action_min - projected.automated_time_per_action_min) / 60) * baseline.actions_per_month
 *   errors_avoided_month = baseline.actions_per_month * ((baseline.error_rate_pct - projected.reduced_error_rate_pct) / 100)
 *   compliance_risk_reduction_usd = (baseline.violations_per_year - (baseline.violations_per_year * (1 - projected.compliance_score_target/100))) * baseline.penalty_per_violation_usd
 *   total_savings_month = (time_saved * hourly_rate) + (errors_avoided * cost_per_error) + (compliance_risk_reduction / 12)
 *   net_roi_usd = (total_savings_month * 12) - annual_platform_cost
 *   roi_percentage = (net_roi_usd / annual_platform_cost) * 100
 *   payback_months = annual_platform_cost / total_savings_month (if savings > 0)
 */
export function calculateRoi(
  config: PlaybookRoiConfig,
  formulaType?: RoiFormulaType,
): RoiCalculation {
  const strategy = formulaType ?? RoiFormulaTypeEnum.STANDARD;
  const params = ROI_STRATEGIES[strategy];

  return computeRoiWithStrategy(config, params);
}

/**
 * Calculate ROI for a specific playbook loaded from the database.
 * Automatically determines the formula type from the playbook's industry.
 */
export async function calculateRoiFromPlaybook(
  playbookDbId: string,
): Promise<RoiCalculation> {
  try {
    const playbook = await db.playbook.findUnique({
      where: { id: playbookDbId },
    });

    if (!playbook) {
      throw new Error(`Playbook not found: ${playbookDbId}`);
    }

    // Parse roiConfig from JSON
    const roiConfig = safeParseJson<PlaybookRoiConfig>(playbook.roiConfig);

    if (!roiConfig.baseline || !roiConfig.projected) {
      throw new Error(`Invalid roiConfig for playbook: ${playbook.playbookId}`);
    }

    // Determine formula type from industry
    const formulaType = getIndustryRoiFormula(playbook.industry as Industry);

    return calculateRoi(roiConfig, formulaType);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Failed to calculate ROI for playbook ${playbookDbId}: ${message}`);
  }
}

/**
 * Project month-by-month cumulative ROI for an active playbook activation.
 * Uses the activation's stored ROI projection as the base monthly figure.
 */
export async function projectRoi(
  activation: { playbookDbId: string; selectedTier: string; roiProjection: string },
  months: number,
): Promise<RoiProjection[]> {
  try {
    // Load the playbook to get pricing
    const playbook = await db.playbook.findUnique({
      where: { id: activation.playbookDbId },
    });

    if (!playbook) {
      throw new Error(`Playbook not found: ${activation.playbookDbId}`);
    }

    // Parse the stored ROI calculation from the activation
    const storedRoi = safeParseJson<RoiCalculation>(activation.roiProjection);

    // If no stored ROI, calculate it fresh
    const roiConfig = safeParseJson<PlaybookRoiConfig>(playbook.roiConfig);
    const roi = (storedRoi.net_roi_usd !== undefined && storedRoi.time_saved_hours_month > 0)
      ? storedRoi
      : calculateRoi(roiConfig, getIndustryRoiFormula(playbook.industry as Industry));

    // Determine monthly cost from pricing
    const pricing = safeParseJson<{ currency: string; tiers: Array<{ name: string; price_usd: number }> }>(playbook.pricing);
    const monthlyCostUsd = resolveMonthlyCost(pricing.tiers, activation.selectedTier);

    // Monthly savings = total_savings_month derived from the ROI calculation
    const totalSavingsMonth = roi.compliance_risk_reduction_usd > 0
      ? (roi.time_saved_hours_month * DEFAULT_HOURLY_RATE_USD) +
        (roi.errors_avoided_month * (roiConfig.baseline?.cost_per_error_usd ?? 250)) +
        (roi.compliance_risk_reduction_usd / 12)
      : (roi.net_roi_usd + DEFAULT_ANNUAL_PLATFORM_COST_USD) / 12;

    const projections: RoiProjection[] = [];

    for (let m = 1; m <= months; m++) {
      // Ramp-up: assume 60% efficiency in month 1, 80% in month 2, 100% from month 3
      const rampFactor = m === 1 ? 0.6 : m === 2 ? 0.8 : 1.0;
      const monthlySavings = totalSavingsMonth * rampFactor;

      const cumulativeSavings = projections.length > 0
        ? projections[projections.length - 1].cumulativeSavingsUsd + monthlySavings
        : monthlySavings;
      const cumulativeCost = monthlyCostUsd * m;

      projections.push({
        month: m,
        cumulativeSavingsUsd: round2(cumulativeSavings),
        cumulativeCostUsd: round2(cumulativeCost),
        cumulativeNetRoiUsd: round2(cumulativeSavings - cumulativeCost),
        monthlySavingsUsd: round2(monthlySavings),
        monthlyCostUsd: round2(monthlyCostUsd),
      });
    }

    return projections;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Failed to project ROI: ${message}`);
  }
}

/**
 * Map an industry to the appropriate ROI formula type.
 * Uses the INDUSTRY_ROI_FORMULA_MAP from types.ts.
 */
export function getIndustryRoiFormula(industry: Industry): RoiFormulaType {
  return INDUSTRY_ROI_FORMULA_MAP[industry] ?? RoiFormulaTypeEnum.STANDARD;
}

/**
 * Format an ROI calculation as a human-readable summary report.
 */
export function formatRoiReport(calc: RoiCalculation): string {
  const lines = [
    "═══ ROI Calculation Report ═══",
    "",
    `  Time Saved:           ${calc.time_saved_hours_month.toFixed(1)} hours/month`,
    `  Errors Avoided:       ${calc.errors_avoided_month.toFixed(1)} /month`,
    `  Compliance Reduction: $${calc.compliance_risk_reduction_usd.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/year`,
    "",
    `  Net ROI:              $${calc.net_roi_usd.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/year`,
    `  ROI Percentage:       ${calc.roi_percentage.toFixed(1)}%`,
    `  Payback Period:       ${calc.payback_months.toFixed(1)} months`,
    "",
  ];

  if (calc.roi_percentage >= 200) {
    lines.push("  ✦ Exceptional ROI — strong automation candidate");
  } else if (calc.roi_percentage >= 100) {
    lines.push("  ✦ Strong ROI — recommended for activation");
  } else if (calc.roi_percentage >= 50) {
    lines.push("  ✦ Moderate ROI — consider with optimization");
  } else if (calc.roi_percentage > 0) {
    lines.push("  ✦ Low ROI — review baseline assumptions");
  } else {
    lines.push("  ✦ Negative ROI — not recommended at current parameters");
  }

  return lines.join("\n");
}

// ─── Strategy Computation ───────────────────────────────────────────

/**
 * Core ROI computation with strategy parameters applied.
 * Separates the calculation logic from the strategy selection.
 */
function computeRoiWithStrategy(
  config: PlaybookRoiConfig,
  params: RoiStrategyParams,
): RoiCalculation {
  const { baseline, projected } = config;

  // ─── Standard formula ────────────────────────────────────────────
  // time_saved_hours_month
  const timeDeltaMin = baseline.manual_time_per_action_min - projected.automated_time_per_action_min;
  const timeSavedHoursMonth = (timeDeltaMin / 60) * baseline.actions_per_month;

  // errors_avoided_month
  const errorDeltaPct = baseline.error_rate_pct - projected.reduced_error_rate_pct;
  const errorsAvoidedMonth = baseline.actions_per_month * (errorDeltaPct / 100);

  // compliance_risk_reduction_usd (with industry weight)
  const violationsAfterAutomation = baseline.violations_per_year * (1 - projected.compliance_score_target / 100);
  const violationsAvoided = baseline.violations_per_year - violationsAfterAutomation;
  const complianceRiskReductionUsd = violationsAvoided * baseline.penalty_per_violation_usd * params.complianceWeight;

  // total_savings_month
  const baseSavingsMonth =
    (timeSavedHoursMonth * DEFAULT_HOURLY_RATE_USD) +
    (errorsAvoidedMonth * baseline.cost_per_error_usd) +
    (complianceRiskReductionUsd / 12);

  // Apply industry factor (additional percentage of base savings)
  const industrySavingsMonth = baseSavingsMonth * params.industryFactor;
  const totalSavingsMonth = baseSavingsMonth + industrySavingsMonth;

  // net_roi_usd
  const netRoiUsd = (totalSavingsMonth * 12) - DEFAULT_ANNUAL_PLATFORM_COST_USD;

  // roi_percentage
  const roiPercentage = DEFAULT_ANNUAL_PLATFORM_COST_USD > 0
    ? (netRoiUsd / DEFAULT_ANNUAL_PLATFORM_COST_USD) * 100
    : 0;

  // payback_months
  const paybackMonths = totalSavingsMonth > 0
    ? DEFAULT_ANNUAL_PLATFORM_COST_USD / totalSavingsMonth
    : Infinity;

  return {
    time_saved_hours_month: round2(timeSavedHoursMonth),
    errors_avoided_month: round2(errorsAvoidedMonth),
    compliance_risk_reduction_usd: round2(complianceRiskReductionUsd),
    net_roi_usd: round2(netRoiUsd),
    roi_percentage: round2(roiPercentage),
    payback_months: paybackMonths === Infinity ? 0 : round2(paybackMonths),
  };
}

// ─── Helpers ────────────────────────────────────────────────────────

/** Resolve monthly cost from pricing tiers based on selected tier name */
function resolveMonthlyCost(
  tiers: Array<{ name: string; price_usd: number }> | undefined,
  selectedTier: string,
): number {
  if (!tiers || tiers.length === 0) {
    return DEFAULT_MONTHLY_PLATFORM_COST_USD;
  }

  const tier = tiers.find((t) => t.name === selectedTier);
  if (tier) {
    return tier.price_usd;
  }

  // Fallback: return the middle tier (Pro) or first tier
  return tiers.length >= 2 ? tiers[1].price_usd : tiers[0].price_usd;
}

/** Round a number to 2 decimal places */
function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Safely parse JSON with fallback to empty object */
function safeParseJson<T>(json: string | null | undefined): T {
  try {
    if (!json) return {} as T;
    return JSON.parse(json) as T;
  } catch {
    return {} as T;
  }
}
