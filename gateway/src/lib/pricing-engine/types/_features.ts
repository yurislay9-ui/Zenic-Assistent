// ─── Pricing Engine Features ───────────────────────────────────────────
// Feature name type (must match Rust Feature enum).
// Extracted from pricing-engine/types.ts for modularity.

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
