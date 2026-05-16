// ─── Zenic-Agents v3 — Policy Engine Barrel Export ────────────────────
// Public API — import anything from '@/lib/policy-engine'

// Types
export * from "./types";

// YAML Loader
export {
  loadPolicyFromYaml,
  compilePolicyDocument,
  computeContentHash,
  documentToYaml,
  PolicyValidationError,
  PolicyCompilationError,
} from "./yaml-loader";
export type { YamlLoaderConfig } from "./yaml-loader";

// Evaluator
export {
  PolicyEvaluator,
  getPolicyEvaluator,
  resetPolicyEvaluator,
} from "./evaluator";

// Versioning
export {
  createVersion,
  getVersion,
  listVersions,
  getVersionChain,
  rollbackToVersion,
  activateVersion,
} from "./versioning";

// Testing
export {
  runPolicyTests,
  runAndStoreTests,
  getTestResults,
} from "./testing";

// Diff
export {
  diffPolicies,
  formatDiffSummary,
} from "./diff";

// Hot-Reload
export {
  PolicyHotReloader,
  getPolicyHotReloader,
  resetPolicyHotReloader,
} from "./hot-reload";

// Compliance
export {
  generateComplianceReport,
} from "./compliance-map";

// Composition Engine (Phase 4 — Policy Sets)
export {
  CompositionEngine,
  getCompositionEngine,
  resetCompositionEngine,
} from "./composition";

// Approval Workflow (Phase 4 — Policy Approval Engine)
export {
  createApprovalRequest,
  submitForReview,
  approveRequest,
  deployApproval,
  cancelApproval,
  rollbackApproval,
  checkExpiredApprovals,
  getApprovalRequest,
  listApprovalRequests,
} from "./approval";
export type {
  CreateApprovalRequestInput,
  ApprovalListOptions,
} from "./approval";

// Impact Analysis (Phase 4 — Policy Impact Engine)
export {
  analyzeImpact,
  getImpactAnalysis,
  listImpactAnalyses,
} from "./impact";
export type {
  ImpactAnalysisSummary,
} from "./impact";

// Constraint Solver (Phase 4 — Formal Verification)
export {
  verifyPolicies,
  getVerification,
  listVerifications,
} from "./constraint-solver";
export type {
  ListVerificationsOptions,
} from "./constraint-solver";

// Simulator (Phase 4 — Policy What-If Analysis)
export {
  runSimulation,
  getSimulation,
  listSimulations,
  deleteSimulation,
} from "./simulator";
export type {
  ListSimulationsOptions,
} from "./simulator";

// Conflict Detector (Phase 4 — Cross-Policy Conflict Detection)
export {
  ConflictDetector,
  getConflictDetector,
  resetConflictDetector,
} from "./conflict-detector";

// Template Engine (Phase 4 — Policy Template Engine)
export {
  createTemplate,
  getTemplate,
  listTemplates,
  instantiateTemplate,
  updateTemplate,
  deleteTemplate,
} from "./templates";
export type {
  TemplateListOptions,
} from "./templates";

// Namespace Engine (Phase 4 — Multi-tenant Policy Scoping)
export {
  createNamespace,
  getNamespace,
  listNamespaces,
  evaluateInNamespace,
  getNamespaceHierarchy,
  updateNamespace,
  deleteNamespace,
} from "./namespaces";
