// ─── Pricing Engine Feature Map ────────────────────────────────────────
// Feature availability per tier and tier ordering.
// Extracted from pricing-engine/types.ts for modularity.

import { SubscriptionTierName } from "./_enums";
import type { FeatureName } from "./_features";

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
