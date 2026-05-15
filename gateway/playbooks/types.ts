// ─── Zenic-Agents v3 — Playbooks por Industria Type System ────────────────
// Phase 4: Industry Playbooks with ROI, Pricing, Onboarding, and Certification
//
// Converts 24 industry niches into purchasable playbooks with measurable ROI.
// YAML-native format matching the playbook.zenic.dev/v1 specification.
//
// Design Patterns:
//   - Value Object: immutable playbook documents and ROI projections
//   - Builder: PlaybookDocumentBuilder for fluent construction
//   - Strategy: RoiCalculationStrategy per industry (different formulas)
//   - Factory: OnboardingStepFactory for step generation per playbook type
//   - Singleton: PlaybookEngine instance for the running service

// ─── Core Enums & Constants ────────────────────────────────────────────

/** Playbook API version — matches YAML apiVersion field */
export const PLAYBOOK_API_VERSION = "playbook.zenic.dev/v1" as const;

/** Playbook document kind — matches YAML kind field */
export const PLAYBOOK_KIND = "Playbook" as const;

/** Playbook lifecycle status */
export const PlaybookStatus = {
  DRAFT: "draft",
  ACTIVE: "active",
  CERTIFIED: "certified",
  DEPRECATED: "deprecated",
  ARCHIVED: "archived",
} as const;
export type PlaybookStatus = (typeof PlaybookStatus)[keyof typeof PlaybookStatus];

/** Certification signing status */
export const CertificationStatus = {
  UNSIGNED: "unsigned",
  PENDING: "pending",
  CERTIFIED: "certified",
  REVOKED: "revoked",
} as const;
export type CertificationStatus = (typeof CertificationStatus)[keyof typeof CertificationStatus];

/** Onboarding step types */
export const OnboardingStepType = {
  QUESTION: "question",
  SELECTION: "selection",
  CONFIRMATION: "confirmation",
  AUTO_CONFIG: "auto_config",
} as const;
export type OnboardingStepType = (typeof OnboardingStepType)[keyof typeof OnboardingStepType];

/** Pricing tier names — aligns with SaaS Starter/Pro/Enterprise model */
export const PricingTierName = {
  STARTER: "starter",
  PRO: "pro",
  ENTERPRISE: "enterprise",
} as const;
export type PricingTierName = (typeof PricingTierName)[keyof typeof PricingTierName];

/** Risk levels for playbook capabilities */
export const CapabilityRiskLevel = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
} as const;
export type CapabilityRiskLevel = (typeof CapabilityRiskLevel)[keyof typeof CapabilityRiskLevel];

/** Industry categories — 13+ industries matching the 24-niche matrix */
export const Industry = {
  FINANCIAL_SERVICES: "financial_services",
  HEALTHCARE: "healthcare",
  INSURANCE: "insurance",
  REAL_ESTATE: "real_estate",
  LEGAL: "legal",
  ECOMMERCE: "ecommerce",
  LOGISTICS: "logistics",
  MANUFACTURING: "manufacturing",
  ENERGY: "energy",
  TELECOMMUNICATIONS: "telecommunications",
  GOVERNMENT: "government",
  EDUCATION: "education",
  AGRICULTURE: "agriculture",
  HOSPITALITY: "hospitality",
  RETAIL: "retail",
  CONSTRUCTION: "construction",
  AUTOMOTIVE: "automotive",
  PHARMACEUTICAL: "pharmaceutical",
  MEDIA: "media",
  NONPROFIT: "nonprofit",
  TECHNOLOGY: "technology",
  CONSULTING: "consulting",
  FOOD_BEVERAGE: "food_beverage",
  MINING: "mining",
} as const;
export type Industry = (typeof Industry)[keyof typeof Industry];

/** Capability categories for grouping playbook features */
export const CapabilityCategory = {
  AUTOMATION: "automation",
  COMPLIANCE: "compliance",
  SECURITY: "security",
  ANALYTICS: "analytics",
  INTEGRATION: "integration",
  WORKFLOW: "workflow",
  REPORTING: "reporting",
  MONITORING: "monitoring",
} as const;
export type CapabilityCategory = (typeof CapabilityCategory)[keyof typeof CapabilityCategory];

/** Onboarding session status */
export const OnboardingSessionStatus = {
  NOT_STARTED: "not_started",
  IN_PROGRESS: "in_progress",
  COMPLETED: "completed",
  ABANDONED: "abandoned",
} as const;
export type OnboardingSessionStatus = (typeof OnboardingSessionStatus)[keyof typeof OnboardingSessionStatus];

// ─── Playbook Document Structure (YAML-native) ────────────────────────

/** Playbook metadata — identifies and categorizes the playbook */
export interface PlaybookMetadata {
  /** Unique playbook identifier (e.g., "financial-control-v1") */
  id: string;
  /** Human-readable name in Spanish (e.g., "Control Financiero Automatizado") */
  name: string;
  /** Human-readable name in English (e.g., "Automated Financial Control") */
  name_en: string;
  /** Primary industry this playbook targets */
  industry: Industry;
  /** Specific sub-industry niche (e.g., "banking", "fintech", "crypto") */
  sub_industry: string;
  /** Compliance standards this playbook satisfies */
  compliance: string[];
  /** Emoji or icon identifier for UI display */
  icon: string;
  /** Brand color (hex) for UI theming */
  color: string;
  /** Semantic version (semver) */
  version: string;
  /** Description of what this playbook delivers */
  description: string;
  /** Author of the playbook */
  author: string;
  /** Labels for categorization, filtering, and search */
  labels: Record<string, string>;
}

/** A single capability provided by a playbook */
export interface PlaybookCapability {
  /** Unique capability identifier (e.g., "auto-reconciliation") */
  id: string;
  /** Human-readable name */
  name: string;
  /** What this capability does */
  description: string;
  /** Category for grouping */
  category: CapabilityCategory;
  /** Whether this capability is enabled by default on activation */
  autoEnabled: boolean;
  /** Risk level — high/critical capabilities require explicit approval */
  riskLevel: CapabilityRiskLevel;
}

/** Reference to a DeclPolicy from Phase 3 Policy Engine */
export interface PolicyReference {
  /** Policy ID matching DeclPolicy.id in the policy engine */
  policyId: string;
  /** Human-readable description of why this policy is included */
  reason?: string;
  /** Whether this policy is required or optional for the playbook */
  required: boolean;
}

/** The full declarative playbook document — YAML-native format */
export interface PlaybookDocument {
  /** API version — always "playbook.zenic.dev/v1" */
  apiVersion: typeof PLAYBOOK_API_VERSION;
  /** Document kind — always "Playbook" */
  kind: typeof PLAYBOOK_KIND;
  /** Playbook identification and classification */
  metadata: PlaybookMetadata;
  /** Capabilities this playbook provides */
  capabilities: PlaybookCapability[];
  /** References to policies from the Policy Engine (Phase 3) */
  policies: PolicyReference[];
  /** ROI configuration with baseline, projections, and formulas */
  roi: PlaybookRoiConfig;
  /** Pricing tiers and feature matrix */
  pricing: PlaybookPricing;
  /** Onboarding configuration with guided setup steps */
  onboarding: PlaybookOnboardingConfig;
  /** Cryptographic certification status */
  certification: PlaybookCertification;
}

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

// ─── Pricing System Types ─────────────────────────────────────────────

/** A single pricing tier with features and limits */
export interface PricingTier {
  /** Tier name (starter, pro, or enterprise) */
  name: PricingTierName;
  /** Monthly price in USD */
  price_usd: number;
  /** Features included in this tier */
  features: string[];
  /** Usage limits — keys are capability/metric names, values are limits or "unlimited" */
  limits: Record<string, number | "unlimited">;
  /** Description of who this tier is recommended for */
  recommended_for: string;
}

/** Pricing configuration embedded in the playbook document */
export interface PlaybookPricing {
  /** Currency code (e.g., "USD", "EUR") */
  currency: string;
  /** Available pricing tiers — must include starter, pro, and enterprise */
  tiers: [PricingTier, PricingTier, PricingTier];
}

/** Calculated pricing for a specific tenant selection */
export interface PricingCalculation {
  /** The selected tier */
  selected_tier: PricingTierName;
  /** Monthly cost in USD */
  monthly_cost: number;
  /** Annual cost in USD (usually monthly * 12 with discount) */
  annual_cost: number;
  /** Cost per automated action in USD */
  per_action_cost: number;
  /** Number of actions needed to break even on the investment */
  break_even_actions: number;
}

// ─── Onboarding System Types ──────────────────────────────────────────

/** A single onboarding step — guides the user through playbook setup */
export interface OnboardingStep {
  /** Unique step identifier (e.g., "select-region", "configure-approval-threshold") */
  id: string;
  /** Step title shown to the user */
  title: string;
  /** Detailed description of what this step configures */
  description: string;
  /** Step type — determines UI rendering and validation */
  type: OnboardingStepType;
  /** Field name in the resulting configuration object */
  field: string;
  /** Available options for selection steps */
  options?: Array<{
    /** Option value */
    value: string;
    /** Human-readable label */
    label: string;
    /** Whether this is the default selection */
    default?: boolean;
  }>;
  /** Default value if the user skips this step */
  default_value: unknown;
  /** Whether this step must be completed (cannot be skipped) */
  required: boolean;
}

/** Onboarding configuration embedded in the playbook document */
export interface PlaybookOnboardingConfig {
  /** Ordered list of onboarding steps */
  steps: OnboardingStep[];
  /** Estimated time to complete all steps (minutes) */
  estimated_minutes: number;
}

/** An active onboarding session for a tenant */
export interface OnboardingSession {
  /** Playbook ID being onboarded */
  playbookId: string;
  /** Unique session identifier */
  sessionId: string;
  /** Current session status */
  status: OnboardingSessionStatus;
  /** User answers keyed by step field name */
  answers: Record<string, unknown>;
  /** Snapshot of the generated configuration after completion */
  config_snapshot?: Record<string, unknown>;
  /** Session creation timestamp (ISO 8601) */
  created: string;
  /** Last update timestamp (ISO 8601) */
  updated: string;
}

// ─── Certification System Types ───────────────────────────────────────

/** Cryptographic certification embedded in the playbook document */
export interface PlaybookCertification {
  /** Current certification status */
  status: CertificationStatus;
  /** Identity of the certifying authority */
  signedBy?: string;
  /** Timestamp when the certification was signed (ISO 8601) */
  signedAt?: string;
  /** Cryptographic signature (e.g., RSA/ECDSA hex) */
  signature?: string;
  /** SHA-256 content hash of the canonical playbook document */
  contentHash?: string;
}

/** Request to certify a playbook */
export interface CertificationRequest {
  /** Playbook ID to certify */
  playbookId: string;
  /** Identity of the person or system requesting certification */
  requestedBy: string;
  /** Business justification for certification */
  justification: string;
}

/** Result of a certification attempt */
export interface CertificationResult {
  /** Whether the certification succeeded */
  success: boolean;
  /** The cryptographic signature (if successful) */
  signature?: string;
  /** The SHA-256 content hash of the certified document */
  hash?: string;
  /** Timestamp when the certification was verified (ISO 8601) */
  verifiedAt?: string;
  /** Error message if certification failed */
  error?: string;
}

// ─── Playbook Evaluation & Activation Types ───────────────────────────

/** Request to activate a playbook for a tenant */
export interface PlaybookActivationRequest {
  /** Playbook ID to activate */
  playbookId: string;
  /** Tenant ID requesting activation */
  tenantId: string;
  /** Selected pricing tier */
  selectedTier: PricingTierName;
  /** Custom configuration overrides from onboarding */
  customConfig?: Record<string, unknown>;
}

/** Result of a playbook activation */
export interface PlaybookActivationResult {
  /** Whether the activation succeeded */
  success: boolean;
  /** IDs of policies that were activated from the playbook */
  activatedPolicies: string[];
  /** IDs of MCP tools that were configured from the playbook */
  configuredTools: string[];
  /** Projected ROI based on the selected tier and configuration */
  roiProjection: RoiCalculation;
  /** Human-readable message about the activation outcome */
  message: string;
}

/** Result of evaluating playbook compatibility for a tenant */
export interface PlaybookEvaluationResult {
  /** Whether the playbook is compatible with the tenant's setup */
  compatible: boolean;
  /** Compatibility score (0-100) based on industry, policies, and tools */
  score: number;
  /** Policy IDs referenced by the playbook but missing from the tenant */
  missingPolicies: string[];
  /** Additional policy IDs recommended for full coverage */
  suggestedPolicies: string[];
  /** Non-blocking warnings about potential issues */
  warnings: string[];
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
  price_usd: 299,
  features: [
    "5 automated workflows",
    "Basic compliance checks",
    "Email support",
    "Monthly ROI report",
  ],
  limits: {
    max_workflows: 5,
    max_actions_per_day: 100,
    max_policies: 10,
    team_members: 3,
  },
  recommended_for: "Small teams starting with automation",
};

/** Default pro tier configuration */
export const DEFAULT_PRO_TIER: PricingTier = {
  name: PricingTierName.PRO,
  price_usd: 799,
  features: [
    "25 automated workflows",
    "Advanced compliance & audit",
    "Priority support",
    "Weekly ROI report",
    "Custom policy integration",
    "API access",
  ],
  limits: {
    max_workflows: 25,
    max_actions_per_day: 1000,
    max_policies: 50,
    team_members: 15,
  },
  recommended_for: "Growing businesses with compliance needs",
};

/** Default enterprise tier configuration */
export const DEFAULT_ENTERPRISE_TIER: PricingTier = {
  name: PricingTierName.ENTERPRISE,
  price_usd: 2499,
  features: [
    "Unlimited automated workflows",
    "Full compliance suite with certification",
    "Dedicated support & SLA",
    "Real-time ROI dashboard",
    "Custom policy engine",
    "Full API access",
    "SSO & RBAC integration",
    "On-premise deployment option",
  ],
  limits: {
    max_workflows: "unlimited",
    max_actions_per_day: "unlimited",
    max_policies: "unlimited",
    team_members: "unlimited",
  },
  recommended_for: "Large organizations with strict compliance requirements",
};

/** Default pricing configuration with all three tiers */
export const DEFAULT_PLAYBOOK_PRICING: PlaybookPricing = {
  currency: "USD",
  tiers: [DEFAULT_STARTER_TIER, DEFAULT_PRO_TIER, DEFAULT_ENTERPRISE_TIER],
};

// ─── Default Certification ──────────────────────────────────────────────

/** Default certification for newly created playbooks */
export const DEFAULT_CERTIFICATION: PlaybookCertification = {
  status: CertificationStatus.UNSIGNED,
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

// ─── Playbook Search & Filter Types ────────────────────────────────────

/** Criteria for searching and filtering playbooks */
export interface PlaybookSearchCriteria {
  /** Filter by industry */
  industry?: Industry;
  /** Filter by sub-industry (partial match) */
  sub_industry?: string;
  /** Filter by compliance standard */
  compliance?: string;
  /** Filter by certification status */
  certificationStatus?: CertificationStatus;
  /** Filter by playbook status */
  status?: PlaybookStatus;
  /** Filter by capability ID */
  capabilityId?: string;
  /** Filter by minimum ROI percentage */
  minRoiPercentage?: number;
  /** Filter by maximum pricing tier */
  maxPriceUsd?: number;
  /** Text search across name, description, and labels */
  searchQuery?: string;
  /** Label key-value filter */
  labels?: Record<string, string>;
}

/** Paginated result of playbook search */
export interface PlaybookSearchResult {
  /** Matching playbook documents */
  playbooks: PlaybookDocument[];
  /** Total number of matching playbooks */
  total: number;
  /** Current page offset */
  offset: number;
  /** Page size */
  limit: number;
}

// ─── Playbook Validation Types ─────────────────────────────────────────

/** Validation error in a playbook document */
export interface PlaybookValidationError {
  /** Field path where the error occurred (e.g., "metadata.id", "roi.baseline.actions_per_month") */
  path: string;
  /** Error message */
  message: string;
  /** Error severity */
  severity: "error" | "warning";
  /** Suggested fix */
  suggestion?: string;
}

/** Result of validating a playbook document */
export interface PlaybookValidationResult {
  /** Whether the playbook passed validation */
  valid: boolean;
  /** Validation errors */
  errors: PlaybookValidationError[];
  /** Number of errors */
  errorCount: number;
  /** Number of warnings */
  warningCount: number;
}
