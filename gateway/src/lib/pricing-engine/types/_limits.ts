// ─── Pricing Engine Tier Limits ────────────────────────────────────────
// Tier limits, display names, and recommended-for strings.
// Extracted from pricing-engine/types.ts for modularity.

import { SubscriptionTierName } from "./_enums";
import type { TierLimitsInfo } from "./_interfaces";

// ═══════════════════════════════════════════════════════════════════════════
// Tier Limits — Must match Rust compiled values exactly
// ═══════════════════════════════════════════════════════════════════════════

export const TIER_LIMITS: Record<SubscriptionTierName, TierLimitsInfo> = {
  [SubscriptionTierName.STARTER]: {
    max_workflows: 5,
    max_actions_per_day: 200,
    max_policies: 10,
    max_team_members: 3,
    max_mcp_tools: 10,
    max_approval_requests_per_day: 20,
    max_playbooks: 2,
    max_namespaces: 1,
    max_simulations_per_month: 5,
    audit_retention_days: 30,
    trace_retention_days: 7,
    overage_rate_usdt: 0.15,
    sso_available: false,
    on_premise_available: false,
    custom_rbac: false,
    z3_solver: false,
  },
  [SubscriptionTierName.BUSINESS]: {
    max_workflows: 25,
    max_actions_per_day: 2000,
    max_policies: 50,
    max_team_members: 15,
    max_mcp_tools: 50,
    max_approval_requests_per_day: 200,
    max_playbooks: 8,
    max_namespaces: 5,
    max_simulations_per_month: 25,
    audit_retention_days: 90,
    trace_retention_days: 30,
    overage_rate_usdt: 0.10,
    sso_available: false,
    on_premise_available: false,
    custom_rbac: true,
    z3_solver: false,
  },
  [SubscriptionTierName.ENTERPRISE]: {
    max_workflows: 0,
    max_actions_per_day: 0,
    max_policies: 0,
    max_team_members: 0,
    max_mcp_tools: 0,
    max_approval_requests_per_day: 0,
    max_playbooks: 0,
    max_namespaces: 25,
    max_simulations_per_month: 0,
    audit_retention_days: 365,
    trace_retention_days: 90,
    overage_rate_usdt: 0.0,
    sso_available: true,
    on_premise_available: false,
    custom_rbac: true,
    z3_solver: true,
  },
  [SubscriptionTierName.ON_PREMISE_ENTERPRISE]: {
    max_workflows: 0,
    max_actions_per_day: 0,
    max_policies: 0,
    max_team_members: 0,
    max_mcp_tools: 0,
    max_approval_requests_per_day: 0,
    max_playbooks: 0,
    max_namespaces: 0,
    max_simulations_per_month: 0,
    audit_retention_days: 0,
    trace_retention_days: 0,
    overage_rate_usdt: 0.0,
    sso_available: true,
    on_premise_available: true,
    custom_rbac: true,
    z3_solver: true,
  },
  [SubscriptionTierName.TRIAL]: {
    // Trial uses Business limits
    max_workflows: 25,
    max_actions_per_day: 2000,
    max_policies: 50,
    max_team_members: 15,
    max_mcp_tools: 50,
    max_approval_requests_per_day: 200,
    max_playbooks: 8,
    max_namespaces: 5,
    max_simulations_per_month: 25,
    audit_retention_days: 90,
    trace_retention_days: 30,
    overage_rate_usdt: 0.10,
    sso_available: false,
    on_premise_available: false,
    custom_rbac: true,
    z3_solver: false,
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// Tier Display Names & Recommended For
// ═══════════════════════════════════════════════════════════════════════════

export const TIER_DISPLAY_NAMES: Record<SubscriptionTierName, string> = {
  [SubscriptionTierName.STARTER]: "Starter",
  [SubscriptionTierName.BUSINESS]: "Business",
  [SubscriptionTierName.ENTERPRISE]: "Enterprise",
  [SubscriptionTierName.ON_PREMISE_ENTERPRISE]: "On-Premise Enterprise",
  [SubscriptionTierName.TRIAL]: "Trial (14 days)",
};

export const TIER_RECOMMENDED_FOR: Record<SubscriptionTierName, string> = {
  [SubscriptionTierName.STARTER]: "Equipos peque\u00f1os que inician con automatizaci\u00f3n",
  [SubscriptionTierName.BUSINESS]: "Empresas en crecimiento con necesidades de compliance",
  [SubscriptionTierName.ENTERPRISE]: "Organizaciones grandes con requisitos estrictos de compliance",
  [SubscriptionTierName.ON_PREMISE_ENTERPRISE]: "Organizaciones que requieren privacidad total y despliegue propio",
  [SubscriptionTierName.TRIAL]: "Acceso completo al Plan Business por 14 d\u00edas sin tarjeta",
};
