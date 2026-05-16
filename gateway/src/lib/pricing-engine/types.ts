// ─── Zenic-Agents v3 — Pricing Engine Types (TypeScript) ────────────────
// USDT TRC20 ONLY. All pricing types mirror the compiled Rust engine.
// These types are used by both the WASM bridge and the TS fallback.

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

// ═══════════════════════════════════════════════════════════════════════════
// Payment Verification — Manual/Semi-Manual Only
// ═══════════════════════════════════════════════════════════════════════════

export const PaymentVerificationMethod = {
  MANUAL_ADMIN: "manual_admin",
  SEMI_MANUAL_ONCHAIN: "semi_manual_onchain",
} as const;
export type PaymentVerificationMethod = (typeof PaymentVerificationMethod)[keyof typeof PaymentVerificationMethod];

export const ManualPaymentStatus = {
  AWAITING_PAYMENT: "awaiting_payment",
  AWAITING_TX_HASH: "awaiting_tx_hash",
  AWAITING_CONFIRMATION: "awaiting_confirmation",
  CONFIRMED: "confirmed",
  REJECTED: "rejected",
  EXPIRED: "expired",
} as const;
export type ManualPaymentStatus = (typeof ManualPaymentStatus)[keyof typeof ManualPaymentStatus];

export interface PaymentVerificationMethodInfo {
  id: string;
  display_name: string;
  description: string;
  currency: string;
  network: string;
}

export interface ManualPaymentVerification {
  payment_id: string;
  subscription_id: string;
  amount_usdt: number;
  wallet_from: string;
  wallet_to: string;
  tx_hash: string | null;
  verification_method: PaymentVerificationMethod;
  status: ManualPaymentStatus;
  admin_notes: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  created_at: string;
}

export interface ManualPaymentRequest {
  payment_request: ManualPaymentVerification;
  instructions: {
    step1: string;
    step2: string;
    step3: string;
    step4: string;
  };
  platform_wallet: string;
  amount_usdt: number;
  payment_currency: string;
  payment_network: string;
  estimated_confirmation_time: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Feature Gate Map — Must match Rust feature_available() exactly
// ═══════════════════════════════════════════════════════════════════════════

/** All paid tier names (excludes trial) */
export const PAID_TIER_NAMES: SubscriptionTierName[] = [
  SubscriptionTierName.STARTER,
  SubscriptionTierName.BUSINESS,
  SubscriptionTierName.ENTERPRISE,
  SubscriptionTierName.ON_PREMISE_ENTERPRISE,
];

/** All tier names including trial */
export const ALL_TIER_NAMES: SubscriptionTierName[] = [
  SubscriptionTierName.STARTER,
  SubscriptionTierName.BUSINESS,
  SubscriptionTierName.ENTERPRISE,
  SubscriptionTierName.ON_PREMISE_ENTERPRISE,
  SubscriptionTierName.TRIAL,
];

/**
 * Feature availability per tier.
 * Key = feature name, Value = set of tiers that have access.
 * This MUST match the Rust feature_available() function exactly.
 */
export const FEATURE_TIER_MAP: Record<FeatureName, SubscriptionTierName[]> = {
  // MCP Features
  McpToolExecution: ALL_TIER_NAMES.slice(),
  McpCustomTools: ["business", "enterprise", "on_premise_enterprise", "trial"],
  McpToolRegistration: ["business", "enterprise", "on_premise_enterprise", "trial"],
  McpRateLimiting: ALL_TIER_NAMES.slice(),
  McpAuthApiKey: ALL_TIER_NAMES.slice(),
  McpAuthOAuth2: ["business", "enterprise", "on_premise_enterprise", "trial"],
  McpAuthMTls: ["enterprise", "on_premise_enterprise"],
  McpMerkleAudit: ALL_TIER_NAMES.slice(),

  // RBAC Features
  RbacBasicRoles: ALL_TIER_NAMES.slice(),
  RbacCustomRoles: ["business", "enterprise", "on_premise_enterprise", "trial"],
  RbacDangerousPermApproval: ["business", "enterprise", "on_premise_enterprise", "trial"],
  RbacSsoIntegration: ["enterprise", "on_premise_enterprise"],

  // Observability Features
  ObservabilityTracing: ALL_TIER_NAMES.slice(),
  ObservabilityBusinessMetrics: ALL_TIER_NAMES.slice(),
  ObservabilitySecurityMetrics: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ObservabilityResilienceMetrics: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ObservabilityOtelExport: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ObservabilityJsonExport: ALL_TIER_NAMES.slice(),
  ObservabilityCustomDashboards: ["enterprise", "on_premise_enterprise"],

  // Policy Features
  PolicyDeclarativeYaml: ALL_TIER_NAMES.slice(),
  PolicyVersioning: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyTesting: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyHotReload: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyComplianceMapping: ALL_TIER_NAMES.slice(),
  PolicyComposition: ["enterprise", "on_premise_enterprise"],
  PolicyConflictDetection: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyConstraintSolver: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicySimulation: ["enterprise", "on_premise_enterprise"],
  PolicyNamespaces: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyTemplates: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyApprovalWorkflow: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PolicyImpactAnalysis: ["enterprise", "on_premise_enterprise"],
  PolicyZ3Solver: ["enterprise", "on_premise_enterprise"],

  // Playbook Features
  PlaybookActivation: ALL_TIER_NAMES.slice(),
  PlaybookCustomYaml: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PlaybookRoiCalculator: ALL_TIER_NAMES.slice(),
  PlaybookOnboardingWizard: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PlaybookCertification: ["business", "enterprise", "on_premise_enterprise", "trial"],
  PlaybookComplianceMap: ALL_TIER_NAMES.slice(),

  // HITL Features
  HitlApprovalWorkflow: ALL_TIER_NAMES.slice(),
  HitlDelegation: ["business", "enterprise", "on_premise_enterprise", "trial"],
  HitlEscalation: ["business", "enterprise", "on_premise_enterprise", "trial"],
  HitlUndoReversible: ["business", "enterprise", "on_premise_enterprise", "trial"],
  HitlEvidence: ["business", "enterprise", "on_premise_enterprise", "trial"],
  HitlJustification: ["business", "enterprise", "on_premise_enterprise", "trial"],
  HitlSlaTracking: ["enterprise", "on_premise_enterprise"],
  HitlAutoApprove: ["business", "enterprise", "on_premise_enterprise", "trial"],
  HitlExpiryAutoRevert: ["enterprise", "on_premise_enterprise"],

  // Audit Features
  AuditBasicLog: ALL_TIER_NAMES.slice(),
  AuditMerkleChain: ["business", "enterprise", "on_premise_enterprise", "trial"],
  AuditComplianceExport: ["business", "enterprise", "on_premise_enterprise", "trial"],

  // Executor Features
  ExecutorBasic: ALL_TIER_NAMES.slice(),
  ExecutorData: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ExecutorStorage: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ExecutorSecurity: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ExecutorAdvanced: ["enterprise", "on_premise_enterprise"],
  ExecutorQueue: ["business", "enterprise", "on_premise_enterprise", "trial"],
  ExecutorMonitoring: ["business", "enterprise", "on_premise_enterprise", "trial"],

  // On-Premise Features
  OnPremiseDeployment: ["on_premise_enterprise"],
  OnPremiseAirGap: ["on_premise_enterprise"],
  OnPremiseCustomBranding: ["on_premise_enterprise"],
  OnPremiseDataResidency: ["on_premise_enterprise"],
};

/**
 * Ordered tier list from lowest to highest (for minimum_tier calculation).
 * Must match the Rust SubscriptionTier ordering.
 */
export const TIER_ORDER: SubscriptionTierName[] = [
  SubscriptionTierName.STARTER,
  SubscriptionTierName.BUSINESS,
  SubscriptionTierName.ENTERPRISE,
  SubscriptionTierName.ON_PREMISE_ENTERPRISE,
  // trial is separate — not part of the upgrade path
];
