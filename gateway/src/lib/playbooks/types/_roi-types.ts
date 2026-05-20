// ─── Zenic-Agents v3 — ROI System Types ────────────────────────────────
// Split from types.ts — ROI baseline, projections, calculation, and formulas

import type { Industry, RoiFormulaType } from "./_enums";
import { Industry as IndustryEnum, RoiFormulaType as RoiFormulaTypeEnum } from "./_enums";

/** Baseline metrics — current manual operational costs before automation */
export interface RoiBaseline {
  /** Average time spent per action manually (minutes) */
  manual_time_per_action_min: number;
  /** Current error rate as percentage (0-100) */
  error_rate_pct: number;
  /** Number of actions performed per month */
  actions_per_month: number;
  /** Cost incurred per error in USD */
  cost_per_error_usd: number;
  /** Number of compliance violations per year */
  violations_per_year: number;
  /** Average penalty per compliance violation in USD */
  penalty_per_violation_usd: number;
}

/** Projected metrics — expected outcomes after playbook activation */
export interface RoiProjected {
  /** Expected time per action after automation (minutes) */
  automated_time_per_action_min: number;
  /** Expected error rate after automation (percentage, 0-100) */
  reduced_error_rate_pct: number;
  /** Target compliance score (0-100) */
  compliance_score_target: number;
  /** Percentage of actions that will be automated (0-100) */
  automation_rate_pct: number;
}

/** Calculated ROI results — derived from baseline + projected + formula */
export interface RoiCalculation {
  /** Hours saved per month from automation */
  time_saved_hours_month: number;
  /** Number of errors avoided per month */
  errors_avoided_month: number;
  /** Annual compliance risk reduction in USD */
  compliance_risk_reduction_usd: number;
  /** Net ROI in USD per year (savings minus costs) */
  net_roi_usd: number;
  /** ROI percentage (e.g., 340 means 340% return) */
  roi_percentage: number;
  /** Months until the playbook pays for itself */
  payback_months: number;
}

/** ROI configuration embedded in the playbook document */
export interface PlaybookRoiConfig {
  /** Current operational baseline metrics */
  baseline: RoiBaseline;
  /** Projected improvements after automation */
  projected: RoiProjected;
  /** Assumptions used in the ROI calculation */
  assumptions: string[];
  /** Pre-computed ROI result (recalculated on baseline/projected changes) */
  calculated?: RoiCalculation;
}

/** Snapshot of live ROI metrics captured from operational data */
export interface RoiMetricsSnapshot {
  /** Actual hours saved in the measurement period */
  actual_time_saved_hours: number;
  /** Actual error reduction percentage observed */
  actual_error_reduction_pct: number;
  /** Actual compliance score achieved */
  actual_compliance_score: number;
  /** Actual automation rate achieved */
  actual_automation_rate_pct: number;
  /** Revenue impact in USD attributable to the playbook */
  revenue_impact_usd: number;
  /** Cost savings in USD for the measurement period */
  cost_savings_usd: number;
  /** Period start date (ISO 8601) */
  period_start: string;
  /** Period end date (ISO 8601) */
  period_end: string;
}

/** Input parameters for the ROI calculation strategy */
export interface RoiCalculationInput {
  /** Baseline operational metrics */
  baseline: RoiBaseline;
  /** Projected improvements */
  projected: RoiProjected;
  /** Monthly cost of the selected pricing tier */
  monthlyCostUsd: number;
  /** Number of working hours per month (default: 160) */
  workingHoursPerMonth?: number;
  /** Average hourly cost of an employee in USD */
  hourlyCostUsd?: number;
}

/** Maps industry to the appropriate ROI formula type */
export const INDUSTRY_ROI_FORMULA_MAP: Record<Industry, RoiFormulaType> = {
  [IndustryEnum.FINANCIAL_SERVICES]: RoiFormulaTypeEnum.FINANCIAL,
  [IndustryEnum.HEALTHCARE]: RoiFormulaTypeEnum.HEALTHCARE,
  [IndustryEnum.INSURANCE]: RoiFormulaTypeEnum.FINANCIAL,
  [IndustryEnum.REAL_ESTATE]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.LEGAL]: RoiFormulaTypeEnum.COMPLIANCE_HEAVY,
  [IndustryEnum.ECOMMERCE]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.LOGISTICS]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.MANUFACTURING]: RoiFormulaTypeEnum.MANUFACTURING,
  [IndustryEnum.ENERGY]: RoiFormulaTypeEnum.COMPLIANCE_HEAVY,
  [IndustryEnum.TELECOMMUNICATIONS]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.GOVERNMENT]: RoiFormulaTypeEnum.COMPLIANCE_HEAVY,
  [IndustryEnum.EDUCATION]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.AGRICULTURE]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.HOSPITALITY]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.RETAIL]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.CONSTRUCTION]: RoiFormulaTypeEnum.MANUFACTURING,
  [IndustryEnum.AUTOMOTIVE]: RoiFormulaTypeEnum.MANUFACTURING,
  [IndustryEnum.PHARMACEUTICAL]: RoiFormulaTypeEnum.COMPLIANCE_HEAVY,
  [IndustryEnum.MEDIA]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.NONPROFIT]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.TECHNOLOGY]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.CONSULTING]: RoiFormulaTypeEnum.STANDARD,
  [IndustryEnum.FOOD_BEVERAGE]: RoiFormulaTypeEnum.MANUFACTURING,
  [IndustryEnum.MINING]: RoiFormulaTypeEnum.COMPLIANCE_HEAVY,
} as const;
