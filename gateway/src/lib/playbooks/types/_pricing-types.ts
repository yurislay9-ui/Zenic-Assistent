// ─── Zenic-Agents v3 — Pricing System Types ────────────────────────────
// Split from types.ts — pricing tiers, default tiers, and pricing configuration

import type { PricingTierName } from "./_enums";
import { PricingTierName as PricingTierNameEnum } from "./_enums";

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

// ─── Default Pricing Tiers ─────────────────────────────────────────────

/** Default starter tier configuration */
export const DEFAULT_STARTER_TIER: PricingTier = {
  name: PricingTierNameEnum.STARTER,
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
  name: PricingTierNameEnum.BUSINESS,
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
  name: PricingTierNameEnum.ENTERPRISE,
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
  name: PricingTierNameEnum.ON_PREMISE_ENTERPRISE,
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
  name: PricingTierNameEnum.TRIAL,
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
