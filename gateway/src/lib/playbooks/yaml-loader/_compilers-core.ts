// ─── Zenic-Agents v3 — YAML Loader Compilers: Core Sections ──────────
// Split from _compilers.ts — metadata, capability, policy, onboarding, certification

import type {
  PlaybookMetadata,
  PlaybookCapability,
  PolicyReference,
  PlaybookOnboardingConfig,
  OnboardingStep,
  PlaybookCertification,
  Industry,
  CapabilityCategory,
  CapabilityRiskLevel,
  OnboardingStepType,
  CertificationStatus,
} from "../types";
import { CertificationStatus as CertificationStatusEnum } from "../types";
import { PlaybookValidationError } from "./_types";
import type { PlaybookYamlLoaderConfig } from "./_types";
import {
  VALID_INDUSTRIES,
  VALID_CAPABILITY_CATEGORIES,
  VALID_RISK_LEVELS,
  VALID_STEP_TYPES,
  VALID_CERTIFICATION_STATUSES,
} from "./_types";

// ─── Metadata Compilation ─────────────────────────────────────────────

export function compileMetadata(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookMetadata {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("metadata must be an object", "metadata");
  }

  const obj = raw as Record<string, unknown>;

  if (!obj.id || typeof obj.id !== "string") {
    throw new PlaybookValidationError("metadata.id is required and must be a string", "metadata.id");
  }
  if (!obj.name || typeof obj.name !== "string") {
    throw new PlaybookValidationError("metadata.name is required and must be a string", "metadata.name");
  }
  if (!obj.industry || typeof obj.industry !== "string") {
    throw new PlaybookValidationError("metadata.industry is required and must be a string", "metadata.industry");
  }

  if (config.strictValidation && !VALID_INDUSTRIES.has(obj.industry as string)) {
    throw new PlaybookValidationError(
      `Invalid industry "${String(obj.industry)}". Must be one of: ${[...VALID_INDUSTRIES].join(", ")}`,
      "metadata.industry",
      obj.industry,
    );
  }

  if (obj.version && config.strictValidation) {
    if (typeof obj.version === "string" && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/.test(obj.version)) {
      throw new PlaybookValidationError(
        `Invalid semver format: "${String(obj.version)}"`,
        "metadata.version",
        obj.version,
      );
    }
  }

  const name_en = typeof obj.name_en === "string" ? obj.name_en : obj.name as string;
  const sub_industry = typeof obj.sub_industry === "string" ? obj.sub_industry : "";
  const description = typeof obj.description === "string" ? obj.description : "";
  const author = typeof obj.author === "string" ? obj.author : config.defaultAuthor;
  const icon = typeof obj.icon === "string" ? obj.icon : "📋";
  const color = typeof obj.color === "string" ? obj.color : "#6b7280";
  const version = typeof obj.version === "string" ? obj.version : "1.0.0";

  const compliance = Array.isArray(obj.compliance)
    ? obj.compliance.map(String)
    : [];

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

export function compileCapability(
  raw: unknown,
  index: number,
  config: PlaybookYamlLoaderConfig,
): PlaybookCapability {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`capabilities[${index}] must be an object`, `capabilities[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `capabilities[${index}]`;

  if (!obj.id || typeof obj.id !== "string") {
    throw new PlaybookValidationError(`${prefix}.id is required and must be a string`, `${prefix}.id`);
  }
  if (!obj.name || typeof obj.name !== "string") {
    throw new PlaybookValidationError(`${prefix}.name is required and must be a string`, `${prefix}.name`);
  }
  if (!obj.description || typeof obj.description !== "string") {
    throw new PlaybookValidationError(`${prefix}.description is required and must be a string`, `${prefix}.description`);
  }

  const category = typeof obj.category === "string" ? obj.category : "automation";
  if (config.strictValidation && !VALID_CAPABILITY_CATEGORIES.has(category)) {
    throw new PlaybookValidationError(
      `${prefix}.category must be one of: ${[...VALID_CAPABILITY_CATEGORIES].join(", ")}`,
      `${prefix}.category`,
      category,
    );
  }

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

export function compilePolicyReference(
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

// ─── Onboarding Compilation ───────────────────────────────────────────

export function compileOnboarding(
  raw: unknown,
  _config: PlaybookYamlLoaderConfig,
): PlaybookOnboardingConfig {
  if (!raw || typeof raw !== "object") {
    return { steps: [], estimated_minutes: 15 };
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

export function compileOnboardingStep(
  raw: unknown,
  index: number,
): OnboardingStep {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`onboarding.steps[${index}] must be an object`, `onboarding.steps[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `onboarding.steps[${index}]`;

  const type = typeof obj.type === "string" ? obj.type : "question";
  if (!VALID_STEP_TYPES.has(type)) {
    throw new PlaybookValidationError(
      `${prefix}.type must be one of: ${[...VALID_STEP_TYPES].join(", ")}`,
      `${prefix}.type`,
      type,
    );
  }

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

export function compileCertification(
  raw: unknown,
  _config: PlaybookYamlLoaderConfig,
): PlaybookCertification {
  if (!raw || typeof raw !== "object") {
    return { status: CertificationStatusEnum.UNSIGNED };
  }

  const obj = raw as Record<string, unknown>;

  const status = typeof obj.status === "string" ? obj.status : CertificationStatusEnum.UNSIGNED;
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
