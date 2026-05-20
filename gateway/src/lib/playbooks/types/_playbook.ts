// ─── Zenic-Agents v3 — Playbooks Document & Onboarding Types ──────────
// Playbook document structure, onboarding, certification, activation,
// evaluation, search, and validation types.
//
// Design Patterns:
//   - Builder: PlaybookDocumentBuilder for fluent construction
//   - Factory: OnboardingStepFactory for step generation per playbook type

import {
  PLAYBOOK_API_VERSION,
  PLAYBOOK_KIND,
  CertificationStatus as CertificationStatusEnum,
} from "./_core";
import type {
  Industry,
  PlaybookStatus,
  CapabilityCategory,
  CapabilityRiskLevel,
  OnboardingStepType,
  OnboardingSessionStatus,
  CertificationStatus,
  PricingTierName,
  PlaybookPricing,
} from "./_core";
import type {
  RoiCalculation,
  PlaybookRoiConfig,
} from "./_metrics";

// ─── Playbook Document Structure (YAML-native) ────────────────────────

/** Playbook metadata — identifies and categorizes the playbook */
export interface PlaybookMetadata {
  /** Unique playbook identifier (e.g., "financial-control-v1") */
  id: string;
  /** Human-readable name in Spanish (e.g., "Control Financiero Automatizado") */
  name: string;
  /** Human-readable name in English (e.g., "Automated Financial Control") */
  name_en: string;
  /** Primary industry this playbook targets */
  industry: Industry;
  /** Specific sub-industry niche (e.g., "banking", "fintech", "crypto") */
  sub_industry: string;
  /** Compliance standards this playbook satisfies */
  compliance: string[];
  /** Emoji or icon identifier for UI display */
  icon: string;
  /** Brand color (hex) for UI theming */
  color: string;
  /** Semantic version (semver) */
  version: string;
  /** Description of what this playbook delivers */
  description: string;
  /** Author of the playbook */
  author: string;
  /** Labels for categorization, filtering, and search */
  labels: Record<string, string>;
}

/** A single capability provided by a playbook */
export interface PlaybookCapability {
  /** Unique capability identifier (e.g., "auto-reconciliation") */
  id: string;
  /** Human-readable name */
  name: string;
  /** What this capability does */
  description: string;
  /** Category for grouping */
  category: CapabilityCategory;
  /** Whether this capability is enabled by default on activation */
  autoEnabled: boolean;
  /** Risk level — high/critical capabilities require explicit approval */
  riskLevel: CapabilityRiskLevel;
}

/** Reference to a DeclPolicy from Phase 3 Policy Engine */
export interface PolicyReference {
  /** Policy ID matching DeclPolicy.id in the policy engine */
  policyId: string;
  /** Human-readable description of why this policy is included */
  reason?: string;
  /** Whether this policy is required or optional for the playbook */
  required: boolean;
}

/** The full declarative playbook document — YAML-native format */
export interface PlaybookDocument {
  /** API version — always "playbook.zenic.dev/v1" */
  apiVersion: typeof PLAYBOOK_API_VERSION;
  /** Document kind — always "Playbook" */
  kind: typeof PLAYBOOK_KIND;
  /** Playbook identification and classification */
  metadata: PlaybookMetadata;
  /** Capabilities this playbook provides */
  capabilities: PlaybookCapability[];
  /** References to policies from the Policy Engine (Phase 3) */
  policies: PolicyReference[];
  /** ROI configuration with baseline, projections, and formulas */
  roi: PlaybookRoiConfig;
  /** Pricing tiers and feature matrix */
  pricing: PlaybookPricing;
  /** Onboarding configuration with guided setup steps */
  onboarding: PlaybookOnboardingConfig;
  /** Cryptographic certification status */
  certification: PlaybookCertification;
}

// ─── Onboarding System Types ──────────────────────────────────────────

/** A single onboarding step — guides the user through playbook setup */
export interface OnboardingStep {
  /** Unique step identifier (e.g., "select-region", "configure-approval-threshold") */
  id: string;
  /** Step title shown to the user */
  title: string;
  /** Detailed description of what this step configures */
  description: string;
  /** Step type — determines UI rendering and validation */
  type: OnboardingStepType;
  /** Field name in the resulting configuration object */
  field: string;
  /** Available options for selection steps */
  options?: Array<{
    /** Option value */
    value: string;
    /** Human-readable label */
    label: string;
    /** Whether this is the default selection */
    default?: boolean;
  }>;
  /** Default value if the user skips this step */
  default_value: unknown;
  /** Whether this step must be completed (cannot be skipped) */
  required: boolean;
}

/** Onboarding configuration embedded in the playbook document */
export interface PlaybookOnboardingConfig {
  /** Ordered list of onboarding steps */
  steps: OnboardingStep[];
  /** Estimated time to complete all steps (minutes) */
  estimated_minutes: number;
}

/** An active onboarding session for a tenant */
export interface OnboardingSession {
  /** Playbook ID being onboarded */
  playbookId: string;
  /** Unique session identifier */
  sessionId: string;
  /** Current session status */
  status: OnboardingSessionStatus;
  /** User answers keyed by step field name */
  answers: Record<string, unknown>;
  /** Snapshot of the generated configuration after completion */
  config_snapshot?: Record<string, unknown>;
  /** Session creation timestamp (ISO 8601) */
  created: string;
  /** Last update timestamp (ISO 8601) */
  updated: string;
}

// ─── Certification System Types ───────────────────────────────────────

/** Cryptographic certification embedded in the playbook document */
export interface PlaybookCertification {
  /** Current certification status */
  status: CertificationStatus;
  /** Identity of the certifying authority */
  signedBy?: string;
  /** Timestamp when the certification was signed (ISO 8601) */
  signedAt?: string;
  /** Cryptographic signature (e.g., RSA/ECDSA hex) */
  signature?: string;
  /** SHA-256 content hash of the canonical playbook document */
  contentHash?: string;
}

/** Request to certify a playbook */
export interface CertificationRequest {
  /** Playbook ID to certify */
  playbookId: string;
  /** Identity of the person or system requesting certification */
  requestedBy: string;
  /** Business justification for certification */
  justification: string;
}

/** Result of a certification attempt */
export interface CertificationResult {
  /** Whether the certification succeeded */
  success: boolean;
  /** The cryptographic signature (if successful) */
  signature?: string;
  /** The SHA-256 content hash of the certified document */
  hash?: string;
  /** Timestamp when the certification was verified (ISO 8601) */
  verifiedAt?: string;
  /** Error message if certification failed */
  error?: string;
}

// ─── Playbook Evaluation & Activation Types ───────────────────────────

/** Request to activate a playbook for a tenant */
export interface PlaybookActivationRequest {
  /** Playbook ID to activate */
  playbookId: string;
  /** Tenant ID requesting activation */
  tenantId: string;
  /** Selected pricing tier */
  selectedTier: PricingTierName;
  /** Custom configuration overrides from onboarding */
  customConfig?: Record<string, unknown>;
}

/** Result of a playbook activation */
export interface PlaybookActivationResult {
  /** Whether the activation succeeded */
  success: boolean;
  /** IDs of policies that were activated from the playbook */
  activatedPolicies: string[];
  /** IDs of MCP tools that were configured from the playbook */
  configuredTools: string[];
  /** Projected ROI based on the selected tier and configuration */
  roiProjection: RoiCalculation;
  /** Human-readable message about the activation outcome */
  message: string;
}

/** Result of evaluating playbook compatibility for a tenant */
export interface PlaybookEvaluationResult {
  /** Whether the playbook is compatible with the tenant's setup */
  compatible: boolean;
  /** Compatibility score (0-100) based on industry, policies, and tools */
  score: number;
  /** Policy IDs referenced by the playbook but missing from the tenant */
  missingPolicies: string[];
  /** Additional policy IDs recommended for full coverage */
  suggestedPolicies: string[];
  /** Non-blocking warnings about potential issues */
  warnings: string[];
}

// ─── Playbook Search & Filter Types ────────────────────────────────────

/** Criteria for searching and filtering playbooks */
export interface PlaybookSearchCriteria {
  /** Filter by industry */
  industry?: Industry;
  /** Filter by sub-industry (partial match) */
  sub_industry?: string;
  /** Filter by compliance standard */
  compliance?: string;
  /** Filter by certification status */
  certificationStatus?: CertificationStatus;
  /** Filter by playbook status */
  status?: PlaybookStatus;
  /** Filter by capability ID */
  capabilityId?: string;
  /** Filter by minimum ROI percentage */
  minRoiPercentage?: number;
  /** Filter by maximum pricing tier (USDT) */
  maxPriceUsdt?: number;
  /** Text search across name, description, and labels */
  searchQuery?: string;
  /** Label key-value filter */
  labels?: Record<string, string>;
}

/** Paginated result of playbook search */
export interface PlaybookSearchResult {
  /** Matching playbook documents */
  playbooks: PlaybookDocument[];
  /** Total number of matching playbooks */
  total: number;
  /** Current page offset */
  offset: number;
  /** Page size */
  limit: number;
}

// ─── Playbook Validation Types ─────────────────────────────────────────

/** Validation error in a playbook document */
export interface PlaybookValidationError {
  /** Field path where the error occurred (e.g., "metadata.id", "roi.baseline.actions_per_month") */
  path: string;
  /** Error message */
  message: string;
  /** Error severity */
  severity: "error" | "warning";
  /** Suggested fix */
  suggestion?: string;
}

/** Result of validating a playbook document */
export interface PlaybookValidationResult {
  /** Whether the playbook passed validation */
  valid: boolean;
  /** Validation errors */
  errors: PlaybookValidationError[];
  /** Number of errors */
  errorCount: number;
  /** Number of warnings */
  warningCount: number;
}

// ─── Default Certification ──────────────────────────────────────────────

/** Default certification for newly created playbooks */
export const DEFAULT_CERTIFICATION: PlaybookCertification = {
  status: CertificationStatusEnum.UNSIGNED,
};
