// ─── Zenic-Agents v3 — Playbook YAML Loader: Compiler — Core ───────────
// Metadata, capability, and policy-reference compilation helpers.

import {
  type PlaybookMetadata,
  type PlaybookCapability,
  type PolicyReference,
  type Industry,
  type CapabilityCategory,
  type CapabilityRiskLevel,
} from "../types";

import {
  PlaybookValidationError,
  type PlaybookYamlLoaderConfig,
  VALID_INDUSTRIES,
  VALID_CAPABILITY_CATEGORIES,
  VALID_RISK_LEVELS,
} from "./types";

// ─── Metadata Compilation ─────────────────────────────────────────────

export function compileMetadata(
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
