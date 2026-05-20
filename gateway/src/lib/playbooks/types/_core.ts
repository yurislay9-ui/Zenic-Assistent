// ─── Zenic-Agents v3 — Playbooks Core Enums & Constants ────────────────
// Phase 4: Foundation enums, constants, and structural pricing types
// shared across all playbook sub-modules.
//
// Design Patterns:
//   - Value Object: immutable enum constants and type-safe string literals

// ─── API Constants ────────────────────────────────────────────────────

/** Playbook API version — matches YAML apiVersion field */
export const PLAYBOOK_API_VERSION = "playbook.zenic.dev/v1" as const;

/** Playbook document kind — matches YAML kind field */
export const PLAYBOOK_KIND = "Playbook" as const;

// ─── Lifecycle & Status Enums ─────────────────────────────────────────

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

// ─── Pricing System Types ─────────────────────────────────────────────

/** A single pricing tier with features and limits */
export interface PricingTier {
  /** Tier name (starter, business, enterprise, on_premise_enterprise, or trial) */
  name: PricingTierName;
  /** Monthly price in USDT */
  price_usdt: number;
  /** One-time setup fee in USDT */
  setup_fee_usdt: number;
  /** Features included in this tier */
  features: string[];
  /** Usage limits — keys are capability/metric names, values are limits or "unlimited" */
  limits: Record<string, number | "unlimited">;
  /** Description of who this tier is recommended for */
  recommended_for: string;
  /** Payment currency — always USDT */
  payment_currency: string;
  /** Payment network — always TRC20 */
  payment_network: string;
}

/** Pricing configuration embedded in the playbook document */
export interface PlaybookPricing {
  /** Currency code — always "USDT" */
  currency: string;
  /** Payment network — always "TRC20" */
  network: string;
  /** Available pricing tiers */
  tiers: PricingTier[];
}

/** Calculated pricing for a specific tenant selection */
export interface PricingCalculation {
  /** The selected tier */
  selected_tier: PricingTierName;
  /** Monthly cost in USDT */
  monthly_cost_usdt: number;
  /** Annual cost in USDT (usually monthly * 10 with 2-month discount) */
  annual_cost_usdt: number;
  /** One-time setup fee in USDT */
  setup_fee_usdt: number;
  /** Cost per automated action in USDT */
  per_action_cost: number;
  /** Number of actions needed to break even on the investment */
  break_even_actions: number;
  /** Payment currency — always "USDT" */
  payment_currency: string;
  /** Payment network — always "TRC20" */
  payment_network: string;
}
