// ─── Zenic-Agents v3 — Pricing Engine Types (TypeScript) ────────────────
// USDT TRC20 ONLY. All pricing types mirror the compiled Rust engine.
// These types are used by both the WASM bridge and the TS fallback.
//
// _core.ts — Enum constants, response interfaces, and price tables.

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Tier Names: 5 Levels
// ═══════════════════════════════════════════════════════════════════════════

export const SubscriptionTierName = {
  STARTER: "starter",
  BUSINESS: "business",
  ENTERPRISE: "enterprise",
  ON_PREMISE_ENTERPRISE: "on_premise_enterprise",
  TRIAL: "trial",
} as const;
export type SubscriptionTierName = (typeof SubscriptionTierName)[keyof typeof SubscriptionTierName];

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Status
// ═══════════════════════════════════════════════════════════════════════════

export const SubscriptionStatus = {
  TRIAL: "trial",
  ACTIVE: "active",
  PAST_DUE: "past_due",
  CANCELLED: "cancelled",
  EXPIRED: "expired",
  SUSPENDED: "suspended",
  PENDING_PAYMENT: "pending_payment",
} as const;
export type SubscriptionStatus = (typeof SubscriptionStatus)[keyof typeof SubscriptionStatus];

// ═══════════════════════════════════════════════════════════════════════════
// Payment Method — USDT TRC20 ONLY
// ═══════════════════════════════════════════════════════════════════════════

export const PaymentMethod = {
  USDT_TRC20: "usdt_trc20",
} as const;
export type PaymentMethod = (typeof PaymentMethod)[keyof typeof PaymentMethod];

// ═══════════════════════════════════════════════════════════════════════════
// Payment Status
// ═══════════════════════════════════════════════════════════════════════════

export const PaymentStatus = {
  PENDING: "pending",
  CONFIRMING: "confirming",
  CONFIRMED: "confirmed",
  FAILED: "failed",
  EXPIRED: "expired",
  REFUNDED: "refunded",
} as const;
export type PaymentStatus = (typeof PaymentStatus)[keyof typeof PaymentStatus];

// ═══════════════════════════════════════════════════════════════════════════
// Add-on Identifiers
// ═══════════════════════════════════════════════════════════════════════════

export const AddOnId = {
  EXTRA_WORKFLOW_PACK: "ExtraWorkflowPack",
  EXTRA_TEAM_PACK: "ExtraTeamPack",
  COMPLIANCE_PACK: "CompliancePack",
  ADVANCED_ANALYTICS: "AdvancedAnalytics",
  PRIORITY_SUPPORT: "PrioritySupport",
  Z3_SOLVER_ACCESS: "Z3SolverAccess",
  EXTRA_SIMULATIONS_PACK: "ExtraSimulationsPack",
  AUDIT_EXTENDED_RETENTION: "AuditExtendedRetention",
} as const;
export type AddOnId = (typeof AddOnId)[keyof typeof AddOnId];

// ═══════════════════════════════════════════════════════════════════════════
// Feature Names (must match Rust Feature enum)
// ═══════════════════════════════════════════════════════════════════════════

export type FeatureName =
  | "McpToolExecution" | "McpCustomTools" | "McpToolRegistration" | "McpRateLimiting"
  | "McpAuthApiKey" | "McpAuthOAuth2" | "McpAuthMTls" | "McpMerkleAudit"
  | "RbacBasicRoles" | "RbacCustomRoles" | "RbacDangerousPermApproval" | "RbacSsoIntegration"
  | "ObservabilityTracing" | "ObservabilityBusinessMetrics" | "ObservabilitySecurityMetrics"
  | "ObservabilityResilienceMetrics" | "ObservabilityOtelExport" | "ObservabilityJsonExport"
  | "ObservabilityCustomDashboards"
  | "PolicyDeclarativeYaml" | "PolicyVersioning" | "PolicyTesting" | "PolicyHotReload"
  | "PolicyComplianceMapping" | "PolicyComposition" | "PolicyConflictDetection"
  | "PolicyConstraintSolver" | "PolicySimulation" | "PolicyNamespaces" | "PolicyTemplates"
  | "PolicyApprovalWorkflow" | "PolicyImpactAnalysis" | "PolicyZ3Solver"
  | "PlaybookActivation" | "PlaybookCustomYaml" | "PlaybookRoiCalculator"
  | "PlaybookOnboardingWizard" | "PlaybookCertification" | "PlaybookComplianceMap"
  | "HitlApprovalWorkflow" | "HitlDelegation" | "HitlEscalation" | "HitlUndoReversible"
  | "HitlEvidence" | "HitlJustification" | "HitlSlaTracking" | "HitlAutoApprove"
  | "HitlExpiryAutoRevert"
  | "AuditBasicLog" | "AuditMerkleChain" | "AuditComplianceExport"
  | "ExecutorBasic" | "ExecutorData" | "ExecutorStorage" | "ExecutorSecurity"
  | "ExecutorAdvanced" | "ExecutorQueue" | "ExecutorMonitoring"
  | "OnPremiseDeployment" | "OnPremiseAirGap" | "OnPremiseCustomBranding" | "OnPremiseDataResidency";

// ═══════════════════════════════════════════════════════════════════════════
// Response Types (matching Rust JSON output)
// ═══════════════════════════════════════════════════════════════════════════

export interface TierInfo {
  name: string;
  display_name: string;
  monthly_price_usdt: number;
  annual_price_usdt: number;
  setup_fee_usdt: number;
  recommended_for: string;
  limits: TierLimitsInfo;
  payment_currency: string;
  payment_network: string;
}

export interface TierLimitsInfo {
  max_workflows: number;
  max_actions_per_day: number;
  max_policies: number;
  max_team_members: number;
  max_mcp_tools: number;
  max_approval_requests_per_day: number;
  max_playbooks: number;
  max_namespaces: number;
  max_simulations_per_month: number;
  audit_retention_days: number;
  trace_retention_days: number;
  overage_rate_usdt: number;
  sso_available: boolean;
  on_premise_available: boolean;
  custom_rbac: boolean;
  z3_solver: boolean;
}

export interface AddOnInfo {
  id: string;
  display_name: string;
  monthly_price_usdt: number;
  available_for_tiers: string[];
  payment_currency: string;
  payment_network: string;
}

export interface TrialConfigInfo {
  duration_days: number;
  requires_credit_card: boolean;
  granted_tier: string;
  max_trials_per_email: number;
  auto_convert: boolean;
  notification_schedule: number[];
  mandatory_for_all: boolean;
  trial_is_prerequisite: boolean;
}

export interface PricingCalc {
  tier: string;
  monthly_price_usdt: number;
  annual_price_usdt: number;
  setup_fee_usdt: number;
  add_ons_monthly_usdt: number;
  total_first_month_usdt: number;
  total_monthly_recurring_usdt: number;
  total_annual_usdt: number;
  overage_rate_usdt: number;
  payment_currency: string;
  payment_network: string;
}

export interface TierComp {
  tiers: PricingCalc[];
  recommended_tier: string;
  recommendation_reason: string;
  payment_currency: string;
  payment_network: string;
}

export interface FeatureCheck {
  feature: string;
  tier: string;
  available: boolean;
  minimum_tier: string | null;
  denial_reason: string | null;
}

export interface TierFeatureInfo {
  tier: string;
  display_name: string;
  features: Array<{ feature: string; available: boolean; minimum_tier: string | null }>;
  payment_currency: string;
  payment_network: string;
}

export interface UsageCheck {
  resource: string;
  allowed: boolean;
  current_usage: number;
  max_allowed: number;
  remaining: number;
  overage_charge_usdt: number;
  minimum_tier: string | null;
  feature_available: boolean;
  denial_reason: string | null;
}

export interface AddressValidation {
  address: string;
  valid: boolean;
  network: string;
  currency: string;
  reason: string;
}

export interface TrialSubscription {
  subscription: {
    id: string;
    tenant_id: string;
    tier: string;
    status: string;
    payment_method: string;
    billing_wallet: string;
    add_ons: string[];
    started_at: string;
    current_period_end: string;
    trial_ends_at: string | null;
    auto_renew: boolean;
    last_payment_tx_hash: string | null;
    cancelled_at: string | null;
    cancellation_reason: string | null;
  };
  trial_config: TrialConfigInfo;
  message: string;
  payment_required: boolean;
  payment_currency: string;
  payment_network: string;
}

export interface PaidSubscription {
  subscription: {
    id: string;
    tenant_id: string;
    tier: string;
    status: string;
    payment_method: string;
    billing_wallet: string;
    add_ons: string[];
    started_at: string;
    current_period_end: string;
    trial_ends_at: string | null;
    auto_renew: boolean;
    last_payment_tx_hash: string | null;
    cancelled_at: string | null;
    cancellation_reason: string | null;
  };
  payment_required: number;
  payment_currency: string;
  payment_network: string;
  breakdown: {
    monthly_usdt: number;
    setup_fee_usdt: number;
    first_payment_usdt: number;
  };
  message: string;
}

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
