// ─── Zenic-Agents v3 — Playbooks ROI & Metrics Types ─────────────────
// ROI calculation types, operational metrics, engine configuration,
// default pricing tiers, and industry-specific ROI formulas.
//
// Design Patterns:
//   - Strategy: RoiCalculationStrategy per industry (different formulas)
//   - Value Object: immutable ROI projections and metric snapshots

import type { PricingTierName, Industry, PricingTier, PlaybookPricing } from "./_core";
import { PricingTierName, Industry } from "./_core";

// ─── ROI System Types ─────────────────────────────────────────────────

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

// ─── Playbook Metrics Types ───────────────────────────────────────────

/** Operational metrics for an active playbook — captured from live data */
export interface PlaybookOperationalMetrics {
  /** Number of actions automated per day */
  actions_automated_daily: number;
  /** Number of safety gate blocks per day */
  safety_gate_blocks: number;
  /** Number of approval requests per day */
  approval_requests: number;
  /** Average decision latency in milliseconds */
  avg_decision_latency_ms: number;
  /** Current compliance score (0-100) */
  compliance_score: number;
}

/** Complete metrics snapshot for a playbook at a point in time */
export interface PlaybookMetricsSnapshot {
  /** Playbook ID these metrics belong to */
  playbookId: string;
  /** When this snapshot was captured (ISO 8601) */
  capturedAt: string;
  /** Operational metrics from the live system */
  operational: PlaybookOperationalMetrics;
  /** ROI metrics computed from actual vs projected data */
  roi: RoiMetricsSnapshot;
  /** Uptime percentage for the playbook's automated processes */
  uptime_pct: number;
}

// ─── Playbook Engine Configuration ─────────────────────────────────────

/** Playbook engine configuration */
export interface PlaybookEngineConfig {
  /** Directory containing YAML playbook files */
  playbookDirectory: string;
  /** Whether to auto-load playbooks on startup */
  autoLoad: boolean;
  /** Whether certification verification is enforced */
  enforceCertification: boolean;
  /** Default pricing tier for new activations */
  defaultTier: PricingTierName;
  /** Whether ROI caching is enabled */
  enableRoiCache: boolean;
  /** ROI cache TTL in seconds */
  roiCacheTtlSeconds: number;
  /** Maximum number of playbooks per tenant */
  maxPlaybooksPerTenant: number;
  /** Whether to enable onboarding sessions */
  enableOnboarding: boolean;
  /** Onboarding session timeout in minutes */
  onboardingTimeoutMinutes: number;
}

/** Default engine configuration */
export const DEFAULT_PLAYBOOK_ENGINE_CONFIG: PlaybookEngineConfig = {
  playbookDirectory: "./playbooks",
  autoLoad: true,
  enforceCertification: false,
  defaultTier: PricingTierName.STARTER,
  enableRoiCache: true,
  roiCacheTtlSeconds: 600,
  maxPlaybooksPerTenant: 50,
  enableOnboarding: true,
  onboardingTimeoutMinutes: 60,
};

// ─── Default Pricing Tiers ─────────────────────────────────────────────

/** Default starter tier configuration */
export const DEFAULT_STARTER_TIER: PricingTier = {
  name: PricingTierName.STARTER,
  price_usdt: 29,
  setup_fee_usdt: 0,
  features: [
    "5 automated workflows",
    "Basic compliance checks",
    "Email support",
    "Monthly ROI report",
    "Basic MCP tools (10)",
    "Basic audit log",
  ],
  limits: {
    max_workflows: 5,
    max_actions_per_day: 200,
    max_policies: 10,
    team_members: 3,
    max_mcp_tools: 10,
    max_playbooks: 2,
  },
  recommended_for: "Equipos pequeños que inician con automatización",
  payment_currency: "USDT",
  payment_network: "TRC20",
};

/** Default business tier configuration */
export const DEFAULT_BUSINESS_TIER: PricingTier = {
  name: PricingTierName.BUSINESS,
  price_usdt: 99,
  setup_fee_usdt: 0,
  features: [
    "25 automated workflows",
    "Advanced compliance & audit",
    "Priority support",
    "Weekly ROI report",
    "Custom policy integration",
    "API access",
    "Custom RBAC roles",
    "50 MCP tools",
    "Policy versioning & testing",
    "HITL approval workflow",
  ],
  limits: {
    max_workflows: 25,
    max_actions_per_day: 2000,
    max_policies: 50,
    team_members: 15,
    max_mcp_tools: 50,
    max_playbooks: 8,
  },
  recommended_for: "Empresas en crecimiento con necesidades de compliance",
  payment_currency: "USDT",
  payment_network: "TRC20",
};

/** Default enterprise tier configuration */
export const DEFAULT_ENTERPRISE_TIER: PricingTier = {
  name: PricingTierName.ENTERPRISE,
  price_usdt: 299,
  setup_fee_usdt: 0,
  features: [
    "Unlimited automated workflows",
    "Full compliance suite with certification",
    "Dedicated support & SLA",
    "Real-time ROI dashboard",
    "Custom policy engine",
    "Full API access",
    "SSO & RBAC integration",
    "Unlimited MCP tools",
    "Z3 constraint solver",
    "Policy simulation & what-if",
    "SLA tracking",
    "Extended audit retention (365 days)",
  ],
  limits: {
    max_workflows: "unlimited",
    max_actions_per_day: "unlimited",
    max_policies: "unlimited",
    team_members: "unlimited",
    max_mcp_tools: "unlimited",
    max_playbooks: "unlimited",
  },
  recommended_for: "Organizaciones grandes con requisitos estrictos de compliance",
  payment_currency: "USDT",
  payment_network: "TRC20",
};

/** Default on-premise enterprise tier configuration */
export const DEFAULT_ON_PREMISE_TIER: PricingTier = {
  name: PricingTierName.ON_PREMISE_ENTERPRISE,
  price_usdt: 799,
  setup_fee_usdt: 2000,
  features: [
    "Everything in Enterprise",
    "On-premise deployment",
    "Air-gap capable",
    "Custom branding",
    "Data residency control",
    "Unlimited everything",
    "Forever audit retention",
    "Dedicated infrastructure",
  ],
  limits: {
    max_workflows: "unlimited",
    max_actions_per_day: "unlimited",
    max_policies: "unlimited",
    team_members: "unlimited",
    max_mcp_tools: "unlimited",
    max_playbooks: "unlimited",
    max_namespaces: "unlimited",
  },
  recommended_for: "Organizaciones que requieren privacidad total y despliegue propio",
  payment_currency: "USDT",
  payment_network: "TRC20",
};

/** Default trial tier configuration — 14 days free, full Business access */
export const DEFAULT_TRIAL_TIER: PricingTier = {
  name: PricingTierName.TRIAL,
  price_usdt: 0,
  setup_fee_usdt: 0,
  features: [
    "Full Business plan access",
    "14-day trial period",
    "No credit card required",
    "All Business features included",
  ],
  limits: {
    max_workflows: 25,
    max_actions_per_day: 2000,
    max_policies: 50,
    team_members: 15,
    max_mcp_tools: 50,
    max_playbooks: 8,
  },
  recommended_for: "Acceso completo al Plan Business por 14 días sin tarjeta",
  payment_currency: "USDT",
  payment_network: "TRC20",
};

/** Default pricing configuration with all four paid tiers */
export const DEFAULT_PLAYBOOK_PRICING: PlaybookPricing = {
  currency: "USDT",
  network: "TRC20",
  tiers: [DEFAULT_STARTER_TIER, DEFAULT_BUSINESS_TIER, DEFAULT_ENTERPRISE_TIER, DEFAULT_ON_PREMISE_TIER],
};

// ─── ROI Calculation Helper Types ──────────────────────────────────────

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

/** Industry-specific ROI formula identifier — strategy pattern */
export const RoiFormulaType = {
  /** Standard formula: time savings + error reduction + compliance risk */
  STANDARD: "standard",
  /** Financial formula: includes transaction value and fraud prevention */
  FINANCIAL: "financial",
  /** Healthcare formula: includes patient safety and regulatory penalties */
  HEALTHCARE: "healthcare",
  /** Manufacturing formula: includes production throughput and quality */
  MANUFACTURING: "manufacturing",
  /** Compliance-heavy formula: emphasizes regulatory risk reduction */
  COMPLIANCE_HEAVY: "compliance_heavy",
} as const;
export type RoiFormulaType = (typeof RoiFormulaType)[keyof typeof RoiFormulaType];

/** Maps industry to the appropriate ROI formula type */
export const INDUSTRY_ROI_FORMULA_MAP: Record<Industry, RoiFormulaType> = {
  [Industry.FINANCIAL_SERVICES]: RoiFormulaType.FINANCIAL,
  [Industry.HEALTHCARE]: RoiFormulaType.HEALTHCARE,
  [Industry.INSURANCE]: RoiFormulaType.FINANCIAL,
  [Industry.REAL_ESTATE]: RoiFormulaType.STANDARD,
  [Industry.LEGAL]: RoiFormulaType.COMPLIANCE_HEAVY,
  [Industry.ECOMMERCE]: RoiFormulaType.STANDARD,
  [Industry.LOGISTICS]: RoiFormulaType.STANDARD,
  [Industry.MANUFACTURING]: RoiFormulaType.MANUFACTURING,
  [Industry.ENERGY]: RoiFormulaType.COMPLIANCE_HEAVY,
  [Industry.TELECOMMUNICATIONS]: RoiFormulaType.STANDARD,
  [Industry.GOVERNMENT]: RoiFormulaType.COMPLIANCE_HEAVY,
  [Industry.EDUCATION]: RoiFormulaType.STANDARD,
  [Industry.AGRICULTURE]: RoiFormulaType.STANDARD,
  [Industry.HOSPITALITY]: RoiFormulaType.STANDARD,
  [Industry.RETAIL]: RoiFormulaType.STANDARD,
  [Industry.CONSTRUCTION]: RoiFormulaType.MANUFACTURING,
  [Industry.AUTOMOTIVE]: RoiFormulaType.MANUFACTURING,
  [Industry.PHARMACEUTICAL]: RoiFormulaType.COMPLIANCE_HEAVY,
  [Industry.MEDIA]: RoiFormulaType.STANDARD,
  [Industry.NONPROFIT]: RoiFormulaType.STANDARD,
  [Industry.TECHNOLOGY]: RoiFormulaType.STANDARD,
  [Industry.CONSULTING]: RoiFormulaType.STANDARD,
  [Industry.FOOD_BEVERAGE]: RoiFormulaType.MANUFACTURING,
  [Industry.MINING]: RoiFormulaType.COMPLIANCE_HEAVY,
} as const;
