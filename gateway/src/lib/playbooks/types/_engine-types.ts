// ─── Zenic-Agents v3 — Engine, Search & Validation Types ──────────────
// Split from types.ts — engine config, activation, search, validation, metrics

import type { PricingTierName, CertificationStatus, PlaybookStatus, Industry } from "./_enums";
import { PricingTierName as PricingTierNameEnum, CertificationStatus as CertificationStatusEnum } from "./_enums";
import type { PlaybookDocument } from "./_document-types";
import type { RoiCalculation, RoiMetricsSnapshot } from "./_roi-types";

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

// ─── Playbook Metrics Types ───────────────────────────────────────────

/** Operational metrics for an active playbook — captured from live data */
export interface PlaybookOperationalMetrics {
  /** Number of actions automated per day */
  actions_automated_daily: number;
  /** Number of safety gate blocks per day */
  safety_gate_blocks: number;
  /** Number of approval requests per day */
  approval_requests: number;
  /** Average decision latency in milliseconds */
  avg_decision_latency_ms: number;
  /** Current compliance score (0-100) */
  compliance_score: number;
}

/** Complete metrics snapshot for a playbook at a point in time */
export interface PlaybookMetricsSnapshot {
  /** Playbook ID these metrics belong to */
  playbookId: string;
  /** When this snapshot was captured (ISO 8601) */
  capturedAt: string;
  /** Operational metrics from the live system */
  operational: PlaybookOperationalMetrics;
  /** ROI metrics computed from actual vs projected data */
  roi: RoiMetricsSnapshot;
  /** Uptime percentage for the playbook's automated processes */
  uptime_pct: number;
}

// ─── Playbook Engine Configuration ─────────────────────────────────────

/** Playbook engine configuration */
export interface PlaybookEngineConfig {
  /** Directory containing YAML playbook files */
  playbookDirectory: string;
  /** Whether to auto-load playbooks on startup */
  autoLoad: boolean;
  /** Whether certification verification is enforced */
  enforceCertification: boolean;
  /** Default pricing tier for new activations */
  defaultTier: PricingTierName;
  /** Whether ROI caching is enabled */
  enableRoiCache: boolean;
  /** ROI cache TTL in seconds */
  roiCacheTtlSeconds: number;
  /** Maximum number of playbooks per tenant */
  maxPlaybooksPerTenant: number;
  /** Whether to enable onboarding sessions */
  enableOnboarding: boolean;
  /** Onboarding session timeout in minutes */
  onboardingTimeoutMinutes: number;
}

/** Default engine configuration */
export const DEFAULT_PLAYBOOK_ENGINE_CONFIG: PlaybookEngineConfig = {
  playbookDirectory: "./playbooks",
  autoLoad: true,
  enforceCertification: false,
  defaultTier: PricingTierNameEnum.STARTER,
  enableRoiCache: true,
  roiCacheTtlSeconds: 600,
  maxPlaybooksPerTenant: 50,
  enableOnboarding: true,
  onboardingTimeoutMinutes: 60,
};

/** Default certification for newly created playbooks */
export const DEFAULT_CERTIFICATION: import("./_document-types").PlaybookCertification = {
  status: CertificationStatusEnum.UNSIGNED,
};

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
