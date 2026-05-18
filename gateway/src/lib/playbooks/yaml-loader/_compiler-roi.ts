// ─── Zenic-Agents v3 — Playbook YAML Loader: Compiler — ROI ────────────
// ROI baseline/projected compilation and calculation helpers.

import {
  type PlaybookRoiConfig,
  type RoiBaseline,
  type RoiProjected,
  type RoiCalculation,
} from "../types";

import {
  PlaybookValidationError,
  type PlaybookYamlLoaderConfig,
} from "./types";

// ─── ROI Config Compilation ───────────────────────────────────────────

export function compileRoiConfig(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookRoiConfig {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi must be an object", "roi");
  }

  const obj = raw as Record<string, unknown>;

  // Validate baseline (required)
  if (!obj.baseline || typeof obj.baseline !== "object") {
    throw new PlaybookValidationError("roi.baseline is required and must be an object", "roi.baseline");
  }
  const baseline = compileRoiBaseline(obj.baseline, config);

  // Validate projected (required)
  if (!obj.projected || typeof obj.projected !== "object") {
    throw new PlaybookValidationError("roi.projected is required and must be an object", "roi.projected");
  }
  const projected = compileRoiProjected(obj.projected, config);

  // Optional fields
  const assumptions = Array.isArray(obj.assumptions)
    ? obj.assumptions.map(String)
    : [];

  // Compute calculated ROI if baseline and projected are available
  const calculated = computeRoiCalculation(baseline, projected, 0);

  return {
    baseline,
    projected,
    assumptions,
    calculated,
  };
}

function compileRoiBaseline(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): RoiBaseline {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi.baseline must be an object", "roi.baseline");
  }

  const obj = raw as Record<string, unknown>;
  const prefix = "roi.baseline";

  const requiredNumbers: Array<keyof RoiBaseline> = [
    "manual_time_per_action_min",
    "error_rate_pct",
    "actions_per_month",
    "cost_per_error_usd",
    "violations_per_year",
    "penalty_per_violation_usd",
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

function compileRoiProjected(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): RoiProjected {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi.projected must be an object", "roi.projected");
  }

  const obj = raw as Record<string, unknown>;
  const prefix = "roi.projected";

  const requiredNumbers: Array<keyof RoiProjected> = [
    "automated_time_per_action_min",
    "reduced_error_rate_pct",
    "compliance_score_target",
    "automation_rate_pct",
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

/**
 * Compute derived ROI metrics from baseline and projected inputs.
 */
function computeRoiCalculation(
  baseline: RoiBaseline,
  projected: RoiProjected,
  monthlyCostUsd: number,
): RoiCalculation {
  const workingHoursPerMonth = 160;
  const hourlyCostUsd = 50;

  // Time saved per month (hours)
  const timeSavedPerActionMin = baseline.manual_time_per_action_min - projected.automated_time_per_action_min;
  const automatedActionsPerMonth = baseline.actions_per_month * (projected.automation_rate_pct / 100);
  const time_saved_hours_month = (timeSavedPerActionMin * automatedActionsPerMonth) / 60;

  // Errors avoided per month
  const originalErrorsPerMonth = baseline.actions_per_month * (baseline.error_rate_pct / 100);
  const newErrorsPerMonth = automatedActionsPerMonth * (projected.reduced_error_rate_pct / 100);
  const errors_avoided_month = originalErrorsPerMonth - newErrorsPerMonth;

  // Compliance risk reduction (annual)
  const violationReductionPct = Math.max(0, projected.compliance_score_target - (100 - baseline.error_rate_pct * 5));
  const compliance_risk_reduction_usd = baseline.violations_per_year * baseline.penalty_per_violation_usd * (violationReductionPct / 100);

  // Net ROI (annual)
  const timeSavingsAnnual = time_saved_hours_month * hourlyCostUsd * 12;
  const errorSavingsAnnual = errors_avoided_month * baseline.cost_per_error_usd * 12;
  const totalSavingsAnnual = timeSavingsAnnual + errorSavingsAnnual + compliance_risk_reduction_usd;
  const totalCostAnnual = monthlyCostUsd * 12;
  const net_roi_usd = totalSavingsAnnual - totalCostAnnual;

  // ROI percentage
  const roi_percentage = totalCostAnnual > 0 ? (net_roi_usd / totalCostAnnual) * 100 : 0;

  // Payback months
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
