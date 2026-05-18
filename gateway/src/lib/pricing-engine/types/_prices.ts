// ─── Pricing Engine Prices & Constants ─────────────────────────────────
// Tier prices, add-on prices, trial config, payment constants.
// Extracted from pricing-engine/types.ts for modularity.

import { SubscriptionTierName } from "./_enums";
import type { TrialConfigInfo } from "./_interfaces";

// ═══════════════════════════════════════════════════════════════════════════
// Tier Prices (USDT) — Must match Rust compiled values exactly
// ═══════════════════════════════════════════════════════════════════════════

export const TIER_PRICES_USDT: Record<SubscriptionTierName, { monthly: number; annual: number; setup: number }> = {
  [SubscriptionTierName.STARTER]: { monthly: 29, annual: 290, setup: 0 },
  [SubscriptionTierName.BUSINESS]: { monthly: 99, annual: 990, setup: 0 },
  [SubscriptionTierName.ENTERPRISE]: { monthly: 299, annual: 2990, setup: 0 },
  [SubscriptionTierName.ON_PREMISE_ENTERPRISE]: { monthly: 799, annual: 7990, setup: 2000 },
  [SubscriptionTierName.TRIAL]: { monthly: 0, annual: 0, setup: 0 },
};

export const ADDON_PRICES_USDT: Record<string, number> = {
  ExtraWorkflowPack: 9,
  ExtraTeamPack: 9,
  CompliancePack: 29,
  AdvancedAnalytics: 19,
  PrioritySupport: 49,
  Z3SolverAccess: 29,
  ExtraSimulationsPack: 19,
  AuditExtendedRetention: 19,
};

export const ADDON_DISPLAY_NAMES: Record<string, string> = {
  ExtraWorkflowPack: "Pack +5 Workflows",
  ExtraTeamPack: "Pack +5 Miembros",
  CompliancePack: "Pack +10 Est\u00e1ndares Compliance",
  AdvancedAnalytics: "Analytics Avanzados",
  PrioritySupport: "Soporte Prioritario (SLA 4h)",
  Z3SolverAccess: "Z3 Constraint Solver",
  ExtraSimulationsPack: "Pack +50 Simulaciones",
  AuditExtendedRetention: "Retenci\u00f3n Extendida +365 d\u00edas",
};

export const ADDON_AVAILABLE_TIERS: Record<string, string[]> = {
  ExtraWorkflowPack: ["starter", "business"],
  ExtraTeamPack: ["starter", "business"],
  CompliancePack: ["business", "enterprise"],
  AdvancedAnalytics: ["business", "enterprise"],
  PrioritySupport: ["business", "enterprise"],
  Z3SolverAccess: ["business"],
  ExtraSimulationsPack: ["business"],
  AuditExtendedRetention: ["starter", "business"],
};

export const TRIAL_CONFIG: TrialConfigInfo = {
  duration_days: 14,
  requires_credit_card: false,
  granted_tier: "business",
  max_trials_per_email: 1,
  auto_convert: false,
  notification_schedule: [3, 1, 0],
  mandatory_for_all: true,
  trial_is_prerequisite: true,
};

export const PAYMENT_CURRENCY = "USDT";
export const PAYMENT_NETWORK = "TRC20";
