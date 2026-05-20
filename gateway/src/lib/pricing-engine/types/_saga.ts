// ─── Zenic-Agents v3 — Pricing Engine Types (TypeScript) ────────────────
// USDT TRC20 ONLY. All pricing types mirror the compiled Rust engine.
// These types are used by both the WASM bridge and the TS fallback.
//
// _saga.ts — Tier limits, display names, payment verification, feature gate map.

import {
  type SubscriptionTierName,
  type TrialConfigInfo,
  SubscriptionTierName as SubscriptionTierNameConst,
} from "./_core";

// Re-import for local usage
const SubscriptionTierName = SubscriptionTierNameConst;

// ═══════════════════════════════════════════════════════════════════════════
// Tier Limits — Must match Rust compiled values exactly
// ═══════════════════════════════════════════════════════════════════════════

export const TIER_LIMITS: Record<SubscriptionTierName, import("./_core").TierLimitsInfo> = {
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
export const FEATURE_TIER_MAP: Record<import("./_core").FeatureName, SubscriptionTierName[]> = {
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
