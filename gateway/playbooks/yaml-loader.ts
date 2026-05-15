// ─── Zenic-Agents v3 — Playbook YAML Loader ──────────────────────────────
// Loads and compiles YAML playbook files into PlaybookDocument objects.
// Uses js-yaml for parsing with strict validation matching playbook.zenic.dev/v1 spec.
//
// Pattern: Strategy — pluggable validation and compilation steps
// Mirrors: policy-engine/yaml-loader.ts

import yaml from "js-yaml";
import { createHash } from "crypto";
import {
  PLAYBOOK_API_VERSION,
  PLAYBOOK_KIND,
  CertificationStatus,
  PricingTierName,
  type PlaybookDocument,
  type PlaybookMetadata,
  type PlaybookCapability,
  type PolicyReference,
  type PlaybookRoiConfig,
  type RoiBaseline,
  type RoiProjected,
  type RoiCalculation,
  type PlaybookPricing,
  type PricingTier,
  type PlaybookOnboardingConfig,
  type OnboardingStep,
  type PlaybookCertification,
  type PlaybookValidationError as PlaybookValidationErrorCode,
  type PlaybookValidationResult,
  type Industry,
  type CapabilityCategory,
  type CapabilityRiskLevel,
  type OnboardingStepType,
} from "./types";

// ─── Validation Errors ────────────────────────────────────────────────

export class PlaybookValidationError extends Error {
  constructor(
    message: string,
    public readonly field: string,
    public readonly value?: unknown,
  ) {
    super(`Playbook validation error at "${field}": ${message}`);
    this.name = "PlaybookValidationError";
  }
}

export class PlaybookCompilationError extends Error {
  constructor(
    message: string,
    public readonly playbookId?: string,
  ) {
    super(`Playbook compilation error${playbookId ? ` for "${playbookId}"` : ""}: ${message}`);
    this.name = "PlaybookCompilationError";
  }
}

// ─── Loader Configuration ─────────────────────────────────────────────

export interface PlaybookYamlLoaderConfig {
  /** Whether to validate on load */
  strictValidation: boolean;
  /** Whether to allow unknown fields */
  allowUnknownFields: boolean;
  /** Whether to compute content hash */
  computeHash: boolean;
  /** Default author if not specified */
  defaultAuthor: string;
}

const DEFAULT_LOADER_CONFIG: PlaybookYamlLoaderConfig = {
  strictValidation: true,
  allowUnknownFields: false,
  computeHash: true,
  defaultAuthor: "system",
};

// ─── Valid Constants ──────────────────────────────────────────────────

const VALID_INDUSTRIES: ReadonlySet<string> = new Set<string>([
  "financial_services", "healthcare", "insurance", "real_estate",
  "legal", "ecommerce", "logistics", "manufacturing",
  "energy", "telecommunications", "government", "education",
  "agriculture", "hospitality", "retail", "construction",
  "automotive", "pharmaceutical", "media", "nonprofit",
  "technology", "consulting", "food_beverage", "mining",
]);

const VALID_CAPABILITY_CATEGORIES: ReadonlySet<string> = new Set<string>([
  "automation", "compliance", "security", "analytics",
  "integration", "workflow", "reporting", "monitoring",
]);

const VALID_RISK_LEVELS: ReadonlySet<string> = new Set<string>([
  "low", "medium", "high", "critical",
]);

const VALID_STEP_TYPES: ReadonlySet<string> = new Set<string>([
  "question", "selection", "confirmation", "auto_config",
]);

const VALID_TIER_NAMES: ReadonlySet<string> = new Set<string>([
  "starter", "pro", "enterprise",
]);

const VALID_CERTIFICATION_STATUSES: ReadonlySet<string> = new Set<string>([
  "unsigned", "pending", "certified", "revoked",
]);

// ─── Core Loader Functions ────────────────────────────────────────────

/**
 * Parse a YAML string into a PlaybookDocument.
 * Validates structure and semantics according to playbook.zenic.dev/v1 spec.
 */
export function loadPlaybookFromYaml(
  yamlContent: string,
  config: Partial<PlaybookYamlLoaderConfig> = {},
): PlaybookDocument {
  const cfg = { ...DEFAULT_LOADER_CONFIG, ...config };

  // 1. Parse YAML
  let raw: unknown;
  try {
    raw = yaml.load(yamlContent);
  } catch (err) {
    throw new PlaybookCompilationError(
      `YAML parse error: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  // 2. Validate and compile
  return compilePlaybookDocument(raw, cfg);
}

/**
 * Validate and compile a raw object into a PlaybookDocument.
 */
export function compilePlaybookDocument(
  raw: unknown,
  config: PlaybookYamlLoaderConfig = DEFAULT_LOADER_CONFIG,
): PlaybookDocument {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("Playbook document must be an object", "root");
  }

  const obj = raw as Record<string, unknown>;

  // Validate apiVersion
  if (obj.apiVersion !== PLAYBOOK_API_VERSION) {
    if (config.strictValidation) {
      throw new PlaybookValidationError(
        `Invalid apiVersion "${String(obj.apiVersion)}". Expected "${PLAYBOOK_API_VERSION}"`,
        "apiVersion",
        obj.apiVersion,
      );
    }
  }

  // Validate kind
  if (obj.kind !== PLAYBOOK_KIND) {
    if (config.strictValidation) {
      throw new PlaybookValidationError(
        `Invalid kind "${String(obj.kind)}". Expected "${PLAYBOOK_KIND}"`,
        "kind",
        obj.kind,
      );
    }
  }

  // Validate metadata
  const metadata = compileMetadata(obj.metadata, config);

  // Validate capabilities
  if (!Array.isArray(obj.capabilities) || obj.capabilities.length === 0) {
    throw new PlaybookValidationError(
      "Playbook must have at least one capability",
      "capabilities",
    );
  }
  const capabilities = obj.capabilities.map((c: unknown, i: number) =>
    compileCapability(c, i, config),
  );

  // Validate policies (optional, can be empty)
  const policies = Array.isArray(obj.policies)
    ? obj.policies.map((p: unknown, i: number) => compilePolicyReference(p, i, config))
    : [];

  // Validate ROI config
  const roi = compileRoiConfig(obj.roi, config);

  // Validate pricing
  const pricing = compilePricing(obj.pricing, config);

  // Validate onboarding
  const onboarding = compileOnboarding(obj.onboarding, config);

  // Validate certification (optional, defaults to unsigned)
  const certification = compileCertification(obj.certification, config);

  const doc: PlaybookDocument = {
    apiVersion: PLAYBOOK_API_VERSION,
    kind: PLAYBOOK_KIND,
    metadata,
    capabilities,
    policies,
    roi,
    pricing,
    onboarding,
    certification,
  };

  return doc;
}

// ─── Metadata Compilation ─────────────────────────────────────────────

function compileMetadata(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookMetadata {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("metadata must be an object", "metadata");
  }

  const obj = raw as Record<string, unknown>;

  // Required fields
  if (!obj.id || typeof obj.id !== "string") {
    throw new PlaybookValidationError("metadata.id is required and must be a string", "metadata.id");
  }
  if (!obj.name || typeof obj.name !== "string") {
    throw new PlaybookValidationError("metadata.name is required and must be a string", "metadata.name");
  }
  if (!obj.industry || typeof obj.industry !== "string") {
    throw new PlaybookValidationError("metadata.industry is required and must be a string", "metadata.industry");
  }

  // Validate industry value
  if (config.strictValidation && !VALID_INDUSTRIES.has(obj.industry as string)) {
    throw new PlaybookValidationError(
      `Invalid industry "${String(obj.industry)}". Must be one of: ${[...VALID_INDUSTRIES].join(", ")}`,
      "metadata.industry",
      obj.industry,
    );
  }

  // Validate semver format
  if (obj.version && config.strictValidation) {
    if (typeof obj.version === "string" && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/.test(obj.version)) {
      throw new PlaybookValidationError(
        `Invalid semver format: "${String(obj.version)}"`,
        "metadata.version",
        obj.version,
      );
    }
  }

  // Optional string fields
  const name_en = typeof obj.name_en === "string" ? obj.name_en : obj.name as string;
  const sub_industry = typeof obj.sub_industry === "string" ? obj.sub_industry : "";
  const description = typeof obj.description === "string" ? obj.description : "";
  const author = typeof obj.author === "string" ? obj.author : config.defaultAuthor;
  const icon = typeof obj.icon === "string" ? obj.icon : "📋";
  const color = typeof obj.color === "string" ? obj.color : "#6b7280";
  const version = typeof obj.version === "string" ? obj.version : "1.0.0";

  // Arrays
  const compliance = Array.isArray(obj.compliance)
    ? obj.compliance.map(String)
    : [];

  // Labels
  const labels = obj.labels && typeof obj.labels === "object"
    ? obj.labels as Record<string, string>
    : {};

  return {
    id: obj.id as string,
    name: obj.name as string,
    name_en,
    industry: obj.industry as Industry,
    sub_industry,
    compliance,
    icon,
    color,
    version,
    description,
    author,
    labels,
  };
}

// ─── Capability Compilation ───────────────────────────────────────────

function compileCapability(
  raw: unknown,
  index: number,
  config: PlaybookYamlLoaderConfig,
): PlaybookCapability {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`capabilities[${index}] must be an object`, `capabilities[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `capabilities[${index}]`;

  // Required fields
  if (!obj.id || typeof obj.id !== "string") {
    throw new PlaybookValidationError(`${prefix}.id is required and must be a string`, `${prefix}.id`);
  }
  if (!obj.name || typeof obj.name !== "string") {
    throw new PlaybookValidationError(`${prefix}.name is required and must be a string`, `${prefix}.name`);
  }
  if (!obj.description || typeof obj.description !== "string") {
    throw new PlaybookValidationError(`${prefix}.description is required and must be a string`, `${prefix}.description`);
  }

  // Validate category
  const category = typeof obj.category === "string" ? obj.category : "automation";
  if (config.strictValidation && !VALID_CAPABILITY_CATEGORIES.has(category)) {
    throw new PlaybookValidationError(
      `${prefix}.category must be one of: ${[...VALID_CAPABILITY_CATEGORIES].join(", ")}`,
      `${prefix}.category`,
      category,
    );
  }

  // Validate risk level
  const riskLevel = typeof obj.riskLevel === "string" ? obj.riskLevel : "low";
  if (config.strictValidation && !VALID_RISK_LEVELS.has(riskLevel)) {
    throw new PlaybookValidationError(
      `${prefix}.riskLevel must be one of: ${[...VALID_RISK_LEVELS].join(", ")}`,
      `${prefix}.riskLevel`,
      riskLevel,
    );
  }

  return {
    id: obj.id as string,
    name: obj.name as string,
    description: obj.description as string,
    category: category as CapabilityCategory,
    autoEnabled: typeof obj.autoEnabled === "boolean" ? obj.autoEnabled : false,
    riskLevel: riskLevel as CapabilityRiskLevel,
  };
}

// ─── Policy Reference Compilation ─────────────────────────────────────

function compilePolicyReference(
  raw: unknown,
  index: number,
  _config: PlaybookYamlLoaderConfig,
): PolicyReference {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`policies[${index}] must be an object`, `policies[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `policies[${index}]`;

  if (!obj.policyId || typeof obj.policyId !== "string") {
    throw new PlaybookValidationError(`${prefix}.policyId is required and must be a string`, `${prefix}.policyId`);
  }

  return {
    policyId: obj.policyId as string,
    reason: typeof obj.reason === "string" ? obj.reason : undefined,
    required: typeof obj.required === "boolean" ? obj.required : true,
  };
}

// ─── ROI Config Compilation ───────────────────────────────────────────

function compileRoiConfig(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookRoiConfig {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi must be an object", "roi");
  }

  const obj = raw as Record<string, unknown>;

  // Validate baseline (required)
  if (!obj.baseline || typeof obj.baseline !== "object") {
    throw new PlaybookValidationError("roi.baseline is required and must be an object", "roi.baseline");
  }
  const baseline = compileRoiBaseline(obj.baseline, config);

  // Validate projected (required)
  if (!obj.projected || typeof obj.projected !== "object") {
    throw new PlaybookValidationError("roi.projected is required and must be an object", "roi.projected");
  }
  const projected = compileRoiProjected(obj.projected, config);

  // Optional fields
  const assumptions = Array.isArray(obj.assumptions)
    ? obj.assumptions.map(String)
    : [];

  // Compute calculated ROI if baseline and projected are available
  const calculated = computeRoiCalculation(baseline, projected, 0);

  return {
    baseline,
    projected,
    assumptions,
    calculated,
  };
}

function compileRoiBaseline(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): RoiBaseline {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi.baseline must be an object", "roi.baseline");
  }

  const obj = raw as Record<string, unknown>;
  const prefix = "roi.baseline";

  const requiredNumbers: Array<keyof RoiBaseline> = [
    "manual_time_per_action_min",
    "error_rate_pct",
    "actions_per_month",
    "cost_per_error_usd",
    "violations_per_year",
    "penalty_per_violation_usd",
  ];

  for (const field of requiredNumbers) {
    if (config.strictValidation && typeof obj[field] !== "number") {
      throw new PlaybookValidationError(
        `${prefix}.${field} is required and must be a number`,
        `${prefix}.${field}`,
        obj[field],
      );
    }
  }

  return {
    manual_time_per_action_min: typeof obj.manual_time_per_action_min === "number" ? obj.manual_time_per_action_min : 30,
    error_rate_pct: typeof obj.error_rate_pct === "number" ? obj.error_rate_pct : 5,
    actions_per_month: typeof obj.actions_per_month === "number" ? obj.actions_per_month : 1000,
    cost_per_error_usd: typeof obj.cost_per_error_usd === "number" ? obj.cost_per_error_usd : 50,
    violations_per_year: typeof obj.violations_per_year === "number" ? obj.violations_per_year : 12,
    penalty_per_violation_usd: typeof obj.penalty_per_violation_usd === "number" ? obj.penalty_per_violation_usd : 5000,
  };
}

function compileRoiProjected(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): RoiProjected {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("roi.projected must be an object", "roi.projected");
  }

  const obj = raw as Record<string, unknown>;
  const prefix = "roi.projected";

  const requiredNumbers: Array<keyof RoiProjected> = [
    "automated_time_per_action_min",
    "reduced_error_rate_pct",
    "compliance_score_target",
    "automation_rate_pct",
  ];

  for (const field of requiredNumbers) {
    if (config.strictValidation && typeof obj[field] !== "number") {
      throw new PlaybookValidationError(
        `${prefix}.${field} is required and must be a number`,
        `${prefix}.${field}`,
        obj[field],
      );
    }
  }

  return {
    automated_time_per_action_min: typeof obj.automated_time_per_action_min === "number" ? obj.automated_time_per_action_min : 5,
    reduced_error_rate_pct: typeof obj.reduced_error_rate_pct === "number" ? obj.reduced_error_rate_pct : 0.5,
    compliance_score_target: typeof obj.compliance_score_target === "number" ? obj.compliance_score_target : 95,
    automation_rate_pct: typeof obj.automation_rate_pct === "number" ? obj.automation_rate_pct : 80,
  };
}

/**
 * Compute derived ROI metrics from baseline and projected inputs.
 */
function computeRoiCalculation(
  baseline: RoiBaseline,
  projected: RoiProjected,
  monthlyCostUsd: number,
): RoiCalculation {
  const workingHoursPerMonth = 160;
  const hourlyCostUsd = 50;

  // Time saved per month (hours)
  const timeSavedPerActionMin = baseline.manual_time_per_action_min - projected.automated_time_per_action_min;
  const automatedActionsPerMonth = baseline.actions_per_month * (projected.automation_rate_pct / 100);
  const time_saved_hours_month = (timeSavedPerActionMin * automatedActionsPerMonth) / 60;

  // Errors avoided per month
  const originalErrorsPerMonth = baseline.actions_per_month * (baseline.error_rate_pct / 100);
  const newErrorsPerMonth = automatedActionsPerMonth * (projected.reduced_error_rate_pct / 100);
  const errors_avoided_month = originalErrorsPerMonth - newErrorsPerMonth;

  // Compliance risk reduction (annual)
  const violationReductionPct = Math.max(0, projected.compliance_score_target - (100 - baseline.error_rate_pct * 5));
  const compliance_risk_reduction_usd = baseline.violations_per_year * baseline.penalty_per_violation_usd * (violationReductionPct / 100);

  // Net ROI (annual)
  const timeSavingsAnnual = time_saved_hours_month * hourlyCostUsd * 12;
  const errorSavingsAnnual = errors_avoided_month * baseline.cost_per_error_usd * 12;
  const totalSavingsAnnual = timeSavingsAnnual + errorSavingsAnnual + compliance_risk_reduction_usd;
  const totalCostAnnual = monthlyCostUsd * 12;
  const net_roi_usd = totalSavingsAnnual - totalCostAnnual;

  // ROI percentage
  const roi_percentage = totalCostAnnual > 0 ? (net_roi_usd / totalCostAnnual) * 100 : 0;

  // Payback months
  const monthlySavings = totalSavingsAnnual / 12;
  const payback_months = monthlySavings > 0 ? Math.ceil(totalCostAnnual / monthlySavings) : 999;

  return {
    time_saved_hours_month: Math.round(time_saved_hours_month * 100) / 100,
    errors_avoided_month: Math.round(errors_avoided_month * 100) / 100,
    compliance_risk_reduction_usd: Math.round(compliance_risk_reduction_usd * 100) / 100,
    net_roi_usd: Math.round(net_roi_usd * 100) / 100,
    roi_percentage: Math.round(roi_percentage * 100) / 100,
    payback_months,
  };
}

// ─── Pricing Compilation ──────────────────────────────────────────────

function compilePricing(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookPricing {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("pricing must be an object", "pricing");
  }

  const obj = raw as Record<string, unknown>;

  // Support two YAML formats:
  // 1. Array format: pricing.tiers: [{ name: starter, ... }, ...]
  // 2. Nested format: pricing.starter: { ... }, pricing.pro: { ... }, pricing.enterprise: { ... }
  let tiers: PricingTier[];

  if (Array.isArray(obj.tiers)) {
    // Format 1: Array-based tiers
    tiers = obj.tiers.map((t: unknown, i: number) =>
      compilePricingTier(t, i, config),
    );
  } else {
    // Format 2: Nested key-based tiers (starter, pro, enterprise as separate objects)
    const nestedTiers: PricingTier[] = [];
    const tierKeys = [PricingTierName.STARTER, PricingTierName.PRO, PricingTierName.ENTERPRISE];

    for (const key of tierKeys) {
      const tierData = obj[key];
      if (tierData && typeof tierData === "object") {
        // Inject the name from the key if not present
        const tierObj = { ...(tierData as Record<string, unknown>), name: key };
        nestedTiers.push(compilePricingTier(tierObj, nestedTiers.length, config));
      }
    }

    tiers = nestedTiers;
  }

  // Check that starter and pro tiers exist
  const tierNames = tiers.map((t) => t.name);
  if (!tierNames.includes(PricingTierName.STARTER) || !tierNames.includes(PricingTierName.PRO)) {
    throw new PlaybookValidationError(
      "pricing.tiers must include both 'starter' and 'pro' tiers",
      "pricing.tiers",
    );
  }

  // Ensure exactly 3 tiers (pad with enterprise if missing)
  while (tiers.length < 3) {
    tiers.push({
      name: PricingTierName.ENTERPRISE,
      price_usd: 2499,
      features: ["Custom pricing"],
      limits: { max_workflows: "unlimited" as const },
      recommended_for: "Large organizations",
    });
  }

  return {
    currency: typeof obj.currency === "string" ? obj.currency : "USD",
    tiers: [tiers[0]!, tiers[1]!, tiers[2]!],
  };
}

function compilePricingTier(
  raw: unknown,
  index: number,
  config: PlaybookYamlLoaderConfig,
): PricingTier {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`pricing.tiers[${index}] must be an object`, `pricing.tiers[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `pricing.tiers[${index}]`;

  // Validate tier name
  const name = typeof obj.name === "string" ? obj.name : "";
  if (config.strictValidation && !VALID_TIER_NAMES.has(name)) {
    throw new PlaybookValidationError(
      `${prefix}.name must be one of: ${[...VALID_TIER_NAMES].join(", ")}`,
      `${prefix}.name`,
      name,
    );
  }

  return {
    name: name as PricingTier["name"],
    price_usd: typeof obj.price_usd === "number" ? obj.price_usd : 0,
    features: Array.isArray(obj.features) ? obj.features.map(String) : [],
    limits: obj.limits && typeof obj.limits === "object"
      ? obj.limits as Record<string, number | "unlimited">
      : {},
    recommended_for: typeof obj.recommended_for === "string" ? obj.recommended_for : "",
  };
}

// ─── Onboarding Compilation ───────────────────────────────────────────

function compileOnboarding(
  raw: unknown,
  _config: PlaybookYamlLoaderConfig,
): PlaybookOnboardingConfig {
  if (!raw || typeof raw !== "object") {
    // Default onboarding config
    return {
      steps: [],
      estimated_minutes: 15,
    };
  }

  const obj = raw as Record<string, unknown>;

  const steps = Array.isArray(obj.steps)
    ? obj.steps.map((s: unknown, i: number) => compileOnboardingStep(s, i))
    : [];

  return {
    steps,
    estimated_minutes: typeof obj.estimated_minutes === "number" ? obj.estimated_minutes : 15,
  };
}

function compileOnboardingStep(
  raw: unknown,
  index: number,
): OnboardingStep {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`onboarding.steps[${index}] must be an object`, `onboarding.steps[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `onboarding.steps[${index}]`;

  // Validate step type
  const type = typeof obj.type === "string" ? obj.type : "question";
  if (!VALID_STEP_TYPES.has(type)) {
    throw new PlaybookValidationError(
      `${prefix}.type must be one of: ${[...VALID_STEP_TYPES].join(", ")}`,
      `${prefix}.type`,
      type,
    );
  }

  // Compile options for selection steps
  let options: OnboardingStep["options"];
  if (Array.isArray(obj.options)) {
    options = obj.options.map((o: unknown) => {
      if (!o || typeof o !== "object") {
        throw new PlaybookValidationError(`${prefix}.options must contain objects`, `${prefix}.options`);
      }
      const opt = o as Record<string, unknown>;
      return {
        value: typeof opt.value === "string" ? opt.value : String(opt.value ?? ""),
        label: typeof opt.label === "string" ? opt.label : String(opt.value ?? ""),
        default: typeof opt.default === "boolean" ? opt.default : undefined,
      };
    });
  }

  return {
    id: typeof obj.id === "string" ? obj.id : `step-${index}`,
    title: typeof obj.title === "string" ? obj.title : `Step ${index + 1}`,
    description: typeof obj.description === "string" ? obj.description : "",
    type: type as OnboardingStepType,
    field: typeof obj.field === "string" ? obj.field : `field_${index}`,
    options,
    default_value: obj.default_value ?? null,
    required: typeof obj.required === "boolean" ? obj.required : false,
  };
}

// ─── Certification Compilation ────────────────────────────────────────

function compileCertification(
  raw: unknown,
  _config: PlaybookYamlLoaderConfig,
): PlaybookCertification {
  if (!raw || typeof raw !== "object") {
    return {
      status: CertificationStatus.UNSIGNED,
    };
  }

  const obj = raw as Record<string, unknown>;

  // Validate certification status
  const status = typeof obj.status === "string" ? obj.status : CertificationStatus.UNSIGNED;
  if (!VALID_CERTIFICATION_STATUSES.has(status)) {
    throw new PlaybookValidationError(
      `certification.status must be one of: ${[...VALID_CERTIFICATION_STATUSES].join(", ")}`,
      "certification.status",
      status,
    );
  }

  return {
    status: status as CertificationStatus,
    signedBy: typeof obj.signedBy === "string" ? obj.signedBy : undefined,
    signedAt: typeof obj.signedAt === "string" ? obj.signedAt : undefined,
    signature: typeof obj.signature === "string" ? obj.signature : undefined,
    contentHash: typeof obj.contentHash === "string" ? obj.contentHash : undefined,
  };
}

// ─── Content Hashing ──────────────────────────────────────────────────

/**
 * Compute SHA-256 content hash for a PlaybookDocument.
 * Uses canonical JSON serialization for deterministic hashing.
 */
export function computePlaybookContentHash(document: PlaybookDocument): string {
  // Deep-sort all keys recursively for deterministic hashing
  const canonical = JSON.stringify(deepSortKeys(document), undefined, 0);
  return createHash("sha256").update(canonical).digest("hex");
}

/** Recursively sort object keys for deterministic serialization */
function deepSortKeys(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(deepSortKeys);
  if (typeof obj === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(obj as Record<string, unknown>).sort()) {
      sorted[key] = deepSortKeys((obj as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return obj;
}

// ─── Validation Helper ────────────────────────────────────────────────

/**
 * Validate a PlaybookDocument and return structured validation results.
 */
export function validatePlaybookDocument(document: PlaybookDocument): PlaybookValidationResult {
  const errors: PlaybookValidationErrorCode[] = [];

  // Validate apiVersion
  if (document.apiVersion !== PLAYBOOK_API_VERSION) {
    errors.push({
      path: "apiVersion",
      message: `Invalid apiVersion "${document.apiVersion}". Expected "${PLAYBOOK_API_VERSION}"`,
      severity: "error",
      suggestion: `Set apiVersion to "${PLAYBOOK_API_VERSION}"`,
    });
  }

  // Validate kind
  if (document.kind !== PLAYBOOK_KIND) {
    errors.push({
      path: "kind",
      message: `Invalid kind "${document.kind}". Expected "${PLAYBOOK_KIND}"`,
      severity: "error",
      suggestion: `Set kind to "${PLAYBOOK_KIND}"`,
    });
  }

  // Validate metadata
  if (!document.metadata.id) {
    errors.push({
      path: "metadata.id",
      message: "metadata.id is required",
      severity: "error",
    });
  }
  if (!document.metadata.name) {
    errors.push({
      path: "metadata.name",
      message: "metadata.name is required",
      severity: "error",
    });
  }
  if (!document.metadata.industry) {
    errors.push({
      path: "metadata.industry",
      message: "metadata.industry is required",
      severity: "error",
    });
  }

  // Validate capabilities
  if (!document.capabilities || document.capabilities.length === 0) {
    errors.push({
      path: "capabilities",
      message: "Playbook must have at least one capability",
      severity: "error",
      suggestion: "Add at least one capability with id, name, and description",
    });
  }

  document.capabilities?.forEach((cap, i) => {
    if (!cap.id) {
      errors.push({ path: `capabilities[${i}].id`, message: "Capability id is required", severity: "error" });
    }
    if (!cap.name) {
      errors.push({ path: `capabilities[${i}].name`, message: "Capability name is required", severity: "error" });
    }
    if (!cap.description) {
      errors.push({ path: `capabilities[${i}].description`, message: "Capability description is required", severity: "warning" });
    }
  });

  // Validate pricing tiers
  const tierNames = document.pricing.tiers.map((t) => t.name);
  if (!tierNames.includes(PricingTierName.STARTER)) {
    errors.push({
      path: "pricing.tiers",
      message: "Pricing must include a 'starter' tier",
      severity: "error",
    });
  }
  if (!tierNames.includes(PricingTierName.PRO)) {
    errors.push({
      path: "pricing.tiers",
      message: "Pricing must include a 'pro' tier",
      severity: "error",
    });
  }

  // Validate ROI config
  if (!document.roi.baseline) {
    errors.push({
      path: "roi.baseline",
      message: "ROI baseline is required",
      severity: "error",
    });
  }
  if (!document.roi.projected) {
    errors.push({
      path: "roi.projected",
      message: "ROI projected is required",
      severity: "error",
    });
  }

  // Validate onboarding steps
  document.onboarding.steps.forEach((step, i) => {
    if (!step.id) {
      errors.push({ path: `onboarding.steps[${i}].id`, message: "Step id is required", severity: "warning" });
    }
    if (!step.title) {
      errors.push({ path: `onboarding.steps[${i}].title`, message: "Step title is required", severity: "warning" });
    }
  });

  // Certification warning for unsigned playbooks
  if (document.certification.status === CertificationStatus.UNSIGNED) {
    errors.push({
      path: "certification.status",
      message: "Playbook is not certified — consider requesting certification for production use",
      severity: "warning",
      suggestion: "Submit a CertificationRequest to sign this playbook",
    });
  }

  const errorCount = errors.filter((e) => e.severity === "error").length;
  const warningCount = errors.filter((e) => e.severity === "warning").length;

  return {
    valid: errorCount === 0,
    errors,
    errorCount,
    warningCount,
  };
}

// ─── YAML Serialization ──────────────────────────────────────────────

/**
 * Serialize a PlaybookDocument back to YAML.
 * Supports round-trip: loadPlaybookFromYaml(documentToYaml(doc)) ≈ doc
 */
export function documentToYaml(document: PlaybookDocument): string {
  const raw = {
    apiVersion: document.apiVersion,
    kind: document.kind,
    metadata: {
      id: document.metadata.id,
      name: document.metadata.name,
      name_en: document.metadata.name_en,
      industry: document.metadata.industry,
      sub_industry: document.metadata.sub_industry,
      compliance: document.metadata.compliance,
      icon: document.metadata.icon,
      color: document.metadata.color,
      version: document.metadata.version,
      description: document.metadata.description,
      author: document.metadata.author,
      ...(Object.keys(document.metadata.labels).length > 0
        ? { labels: document.metadata.labels }
        : {}),
    },
    capabilities: document.capabilities.map((c) => ({
      id: c.id,
      name: c.name,
      description: c.description,
      category: c.category,
      autoEnabled: c.autoEnabled,
      riskLevel: c.riskLevel,
    })),
    ...(document.policies.length > 0
      ? {
          policies: document.policies.map((p) => ({
            policyId: p.policyId,
            ...(p.reason ? { reason: p.reason } : {}),
            required: p.required,
          })),
        }
      : {}),
    roi: {
      baseline: document.roi.baseline,
      projected: document.roi.projected,
      ...(document.roi.assumptions.length > 0
        ? { assumptions: document.roi.assumptions }
        : {}),
      ...(document.roi.calculated ? { calculated: document.roi.calculated } : {}),
    },
    pricing: {
      currency: document.pricing.currency,
      tiers: document.pricing.tiers.map((t) => ({
        name: t.name,
        price_usd: t.price_usd,
        features: t.features,
        limits: t.limits,
        recommended_for: t.recommended_for,
      })),
    },
    onboarding: {
      steps: document.onboarding.steps.map((s) => ({
        id: s.id,
        title: s.title,
        description: s.description,
        type: s.type,
        field: s.field,
        ...(s.options ? { options: s.options } : {}),
        default_value: s.default_value,
        required: s.required,
      })),
      estimated_minutes: document.onboarding.estimated_minutes,
    },
    certification: {
      status: document.certification.status,
      ...(document.certification.signedBy ? { signedBy: document.certification.signedBy } : {}),
      ...(document.certification.signedAt ? { signedAt: document.certification.signedAt } : {}),
      ...(document.certification.signature ? { signature: document.certification.signature } : {}),
      ...(document.certification.contentHash ? { contentHash: document.certification.contentHash } : {}),
    },
  };

  return yaml.dump(raw, {
    indent: 2,
    lineWidth: 120,
    noRefs: true,
    sortKeys: true,
    quotingType: '"',
  });
}
