// ─── Zenic-Agents v3 — Playbooks Enums & Constants ──────────────────────
// Split from types.ts — enums, const objects, and type aliases

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

/** Pricing tier names — aligns with 5-tier USDT TRC20 subscription model */
export const PricingTierName = {
  STARTER: "starter",
  BUSINESS: "business",
  ENTERPRISE: "enterprise",
  ON_PREMISE_ENTERPRISE: "on_premise_enterprise",
  TRIAL: "trial",
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
