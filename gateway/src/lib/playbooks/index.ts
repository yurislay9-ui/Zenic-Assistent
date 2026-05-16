// ─── Zenic-Agents v3 — Playbooks Barrel Export ──────────────────────────
// Public API — import anything from '@/lib/playbooks'

// Types
export * from "./types";

// YAML Loader
export {
  loadPlaybookFromYaml,
  compilePlaybookDocument,
  computePlaybookContentHash,
  documentToYaml,
  validatePlaybookDocument,
  PlaybookValidationError as PlaybookYamlValidationError,
  PlaybookCompilationError,
} from "./yaml-loader";
export type { PlaybookYamlLoaderConfig } from "./yaml-loader";

// Engine
export {
  PlaybookEngine,
  getPlaybookEngine,
  resetPlaybookEngine,
} from "./engine";
export type { PlaybookDbRecord } from "./engine";

// Onboarding Wizard
export {
  createOnboardingSession,
  getOnboardingSession,
  processOnboardingStep,
  completeOnboarding,
  abandonOnboarding,
  generateConfigFromAnswers,
  getOnboardingProgress,
} from "./onboarding-wizard";
export type {
  OnboardingStepResult,
  OnboardingCompletionResult,
  OnboardingProgress,
} from "./onboarding-wizard";

// Certification
export {
  requestCertification,
  verifyCertification,
  revokeCertification,
  generatePlaybookFingerprint,
  getCertificationStatus,
} from "./certification";
export type {
  CertificationVerification,
  CertificationStatusInfo,
} from "./certification";

// ROI Calculator
export {
  calculateRoi,
  calculateRoiFromPlaybook,
  formatRoiReport,
  getIndustryRoiFormula,
} from "./roi-calculator";
export type { RoiProjection } from "./roi-calculator";

// Pricing Engine
export {
  calculatePricing,
  compareTiers,
  estimateCost,
  getRecommendedTier,
  formatPricingReport,
  findTier,
} from "./pricing-engine";
export type {
  TierComparison,
  CostEstimate,
} from "./pricing-engine";

// Compliance Mapper
export {
  mapPlaybookCompliance,
  getIndustryComplianceRequirements,
  calculateComplianceScore,
} from "./compliance-map";
export type {
  ComplianceRequirement,
  StandardCoverage,
  PlaybookComplianceReport,
} from "./compliance-map";

// Metrics Collector
export {
  collectPlaybookMetrics,
  getPlaybookMetricsHistory,
  aggregateIndustryMetrics,
} from "./metrics-collector";
export type { IndustryMetricsSummary } from "./metrics-collector";
