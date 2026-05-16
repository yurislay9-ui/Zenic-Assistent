// ─── Zenic-Agents v3 — YAML Policy Loader ──────────────────────────────
// Loads and compiles YAML policy files into PolicyDocument objects.
// Uses js-yaml for parsing with strict validation.
//
// Pattern: Strategy — pluggable validation and compilation steps

import yaml from "js-yaml";
import { createHash } from "crypto";
import {
  POLICY_API_VERSION,
  POLICY_KIND,
  type PolicyDocument,
  type PolicyMetadata,
  type PolicyStatement,
  type PolicyCondition,
  type PolicyTestCase,
  type ComplianceMapping,
  type ConditionOperator,
} from "./types";

// ─── Validation Errors ────────────────────────────────────────────────

export class PolicyValidationError extends Error {
  constructor(
    message: string,
    public readonly field: string,
    public readonly value?: unknown,
  ) {
    super(`Policy validation error at "${field}": ${message}`);
    this.name = "PolicyValidationError";
  }
}

export class PolicyCompilationError extends Error {
  constructor(
    message: string,
    public readonly policyId?: string,
  ) {
    super(`Policy compilation error${policyId ? ` for "${policyId}"` : ""}: ${message}`);
    this.name = "PolicyCompilationError";
  }
}

// ─── Loader Configuration ─────────────────────────────────────────────

export interface YamlLoaderConfig {
  /** Whether to validate on load */
  strictValidation: boolean;
  /** Whether to allow unknown fields */
  allowUnknownFields: boolean;
  /** Whether to compute content hash */
  computeHash: boolean;
  /** Default author if not specified */
  defaultAuthor: string;
}

const DEFAULT_LOADER_CONFIG: YamlLoaderConfig = {
  strictValidation: true,
  allowUnknownFields: false,
  computeHash: true,
  defaultAuthor: "system",
};

// ─── Valid Operators ──────────────────────────────────────────────────

const VALID_OPERATORS: ReadonlySet<string> = new Set<string>([
  "eq", "neq", "in", "notin", "gt", "lt", "gte", "lte",
  "regex", "exists", "not_exists", "contains", "starts_with", "ends_with",
]);

const VALID_EFFECTS: ReadonlySet<string> = new Set(["allow", "deny", "conditional"]);
const VALID_EXPECTATIONS: ReadonlySet<string> = new Set(["allowed", "denied", "conditional"]);

// ─── Core Loader Functions ────────────────────────────────────────────

/**
 * Parse a YAML string into a PolicyDocument.
 * Validates structure and semantics.
 */
export function loadPolicyFromYaml(
  yamlContent: string,
  config: Partial<YamlLoaderConfig> = {},
): PolicyDocument {
  const cfg = { ...DEFAULT_LOADER_CONFIG, ...config };

  // 1. Parse YAML
  let raw: unknown;
  try {
    raw = yaml.load(yamlContent);
  } catch (err) {
    throw new PolicyCompilationError(
      `YAML parse error: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  // 2. Validate and compile
  return compilePolicyDocument(raw, cfg);
}

/**
 * Validate and compile a raw object into a PolicyDocument.
 */
export function compilePolicyDocument(
  raw: unknown,
  config: YamlLoaderConfig = DEFAULT_LOADER_CONFIG,
): PolicyDocument {
  if (!raw || typeof raw !== "object") {
    throw new PolicyValidationError("Policy document must be an object", "root");
  }

  const obj = raw as Record<string, unknown>;

  // Validate apiVersion
  if (obj.apiVersion !== POLICY_API_VERSION) {
    if (config.strictValidation) {
      throw new PolicyValidationError(
        `Invalid apiVersion "${String(obj.apiVersion)}". Expected "${POLICY_API_VERSION}"`,
        "apiVersion",
        obj.apiVersion,
      );
    }
  }

  // Validate kind
  if (obj.kind !== POLICY_KIND) {
    if (config.strictValidation) {
      throw new PolicyValidationError(
        `Invalid kind "${String(obj.kind)}". Expected "${POLICY_KIND}"`,
        "kind",
        obj.kind,
      );
    }
  }

  // Validate metadata
  const metadata = compileMetadata(obj.metadata, config);

  // Validate statements
  if (!Array.isArray(obj.statements) || obj.statements.length === 0) {
    throw new PolicyValidationError(
      "Policy must have at least one statement",
      "statements",
    );
  }
  const statements = obj.statements.map((s: unknown, i: number) =>
    compileStatement(s, i, config),
  );

  // Validate tests (optional)
  const tests = Array.isArray(obj.tests)
    ? obj.tests.map((t: unknown, i: number) => compileTestCase(t, i, config))
    : undefined;

  return {
    apiVersion: POLICY_API_VERSION,
    kind: POLICY_KIND,
    metadata,
    statements,
    tests,
  };
}

// ─── Metadata Compilation ─────────────────────────────────────────────

function compileMetadata(
  raw: unknown,
  config: YamlLoaderConfig,
): PolicyMetadata {
  if (!raw || typeof raw !== "object") {
    throw new PolicyValidationError("metadata must be an object", "metadata");
  }

  const obj = raw as Record<string, unknown>;

  // Required fields
  if (!obj.id || typeof obj.id !== "string") {
    throw new PolicyValidationError("metadata.id is required and must be a string", "metadata.id");
  }
  if (!obj.name || typeof obj.name !== "string") {
    throw new PolicyValidationError("metadata.name is required and must be a string", "metadata.name");
  }
  if (!obj.version || typeof obj.version !== "string") {
    throw new PolicyValidationError("metadata.version is required and must be a string (semver)", "metadata.version");
  }

  // Validate semver format
  if (config.strictValidation && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/.test(obj.version as string)) {
    throw new PolicyValidationError(
      `Invalid semver format: "${String(obj.version)}"`,
      "metadata.version",
      obj.version,
    );
  }

  if (!obj.description || typeof obj.description !== "string") {
    throw new PolicyValidationError("metadata.description is required", "metadata.description");
  }

  // Optional fields
  const compliance = compileCompliance(obj.compliance);
  const labels = obj.labels && typeof obj.labels === "object"
    ? obj.labels as Record<string, string>
    : undefined;

  return {
    id: obj.id as string,
    name: obj.name as string,
    version: obj.version as string,
    description: obj.description as string,
    compliance,
    labels,
    author: typeof obj.author === "string" ? obj.author : config.defaultAuthor,
    createdAt: typeof obj.createdAt === "string" ? obj.createdAt : new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function compileCompliance(raw: unknown): ComplianceMapping[] | undefined {
  if (!raw || !Array.isArray(raw)) return undefined;

  return raw.map((item: unknown, i: number) => {
    if (!item || typeof item !== "object") {
      throw new PolicyValidationError(`compliance[${i}] must be an object`, `metadata.compliance[${i}]`);
    }
    const obj = item as Record<string, unknown>;

    // Each compliance item has a standard name as key and sections as value
    // Format: { "PCI-DSS": "1.2.3, 1.3.1" } or { "standard": "PCI-DSS", "sections": [...] }
    const keys = Object.keys(obj);
    if (keys.length === 0) {
      throw new PolicyValidationError(`compliance[${i}] must have a standard`, `metadata.compliance[${i}]`);
    }

    const standard = keys[0]!;
    const sectionsValue = obj[standard];

    let sections: string[];
    if (typeof sectionsValue === "string") {
      sections = sectionsValue.split(",").map((s: string) => s.trim()).filter(Boolean);
    } else if (Array.isArray(sectionsValue)) {
      sections = sectionsValue.map(String);
    } else {
      sections = [];
    }

    return {
      standard,
      sections,
      confidence: typeof obj.confidence === "number" ? obj.confidence : 0.8,
    };
  });
}

// ─── Statement Compilation ────────────────────────────────────────────

function compileStatement(
  raw: unknown,
  index: number,
  config: YamlLoaderConfig,
): PolicyStatement {
  if (!raw || typeof raw !== "object") {
    throw new PolicyValidationError(`statements[${index}] must be an object`, `statements[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `statements[${index}]`;

  // Required fields
  if (!obj.id || typeof obj.id !== "string") {
    throw new PolicyValidationError(`${prefix}.id is required`, `${prefix}.id`);
  }

  if (!obj.effect || !VALID_EFFECTS.has(obj.effect as string)) {
    throw new PolicyValidationError(
      `${prefix}.effect must be one of: ${[...VALID_EFFECTS].join(", ")}`,
      `${prefix}.effect`,
      obj.effect,
    );
  }

  if (!obj.resource || typeof obj.resource !== "string") {
    throw new PolicyValidationError(`${prefix}.resource is required`, `${prefix}.resource`);
  }

  if (!obj.action || typeof obj.action !== "string") {
    throw new PolicyValidationError(`${prefix}.action is required`, `${prefix}.action`);
  }

  if (typeof obj.priority !== "number") {
    throw new PolicyValidationError(`${prefix}.priority must be a number`, `${prefix}.priority`);
  }

  // Compile conditions
  const conditions = Array.isArray(obj.conditions)
    ? obj.conditions.map((c: unknown, ci: number) =>
        compileCondition(c, ci, `${prefix}.conditions[${ci}]`, config),
      )
    : undefined;

  return {
    id: obj.id as string,
    effect: obj.effect as PolicyStatement["effect"],
    resource: obj.resource as string,
    action: obj.action as string,
    conditions,
    priority: obj.priority as number,
    description: typeof obj.description === "string" ? obj.description : undefined,
    requiredRole: typeof obj.requiredRole === "string" ? obj.requiredRole : undefined,
    tags: Array.isArray(obj.tags) ? obj.tags.map(String) : undefined,
  };
}

function compileCondition(
  raw: unknown,
  index: number,
  path: string,
  config: YamlLoaderConfig,
): PolicyCondition {
  if (!raw || typeof raw !== "object") {
    throw new PolicyValidationError(`${path} must be an object`, path);
  }

  const obj = raw as Record<string, unknown>;

  if (!obj.field || typeof obj.field !== "string") {
    throw new PolicyValidationError(`${path}.field is required`, `${path}.field`);
  }

  if (!obj.operator || !VALID_OPERATORS.has(obj.operator as string)) {
    throw new PolicyValidationError(
      `${path}.operator must be one of: ${[...VALID_OPERATORS].join(", ")}`,
      `${path}.operator`,
      obj.operator,
    );
  }

  // Validate operator-value compatibility
  if (config.strictValidation) {
    const op = obj.operator as string;
    if (op === "in" || op === "notin") {
      if (!Array.isArray(obj.value)) {
        throw new PolicyValidationError(
          `${path}.value must be an array for operator "${op}"`,
          `${path}.value`,
          obj.value,
        );
      }
    }
    if (op === "exists" || op === "not_exists") {
      // value is ignored for these operators
    }
  }

  return {
    field: obj.field as string,
    operator: obj.operator as ConditionOperator,
    value: obj.value,
    description: typeof obj.description === "string" ? obj.description : undefined,
  };
}

// ─── Test Case Compilation ────────────────────────────────────────────

function compileTestCase(
  raw: unknown,
  index: number,
  config: YamlLoaderConfig,
): PolicyTestCase {
  if (!raw || typeof raw !== "object") {
    throw new PolicyValidationError(`tests[${index}] must be an object`, `tests[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `tests[${index}]`;

  if (!obj.name || typeof obj.name !== "string") {
    throw new PolicyValidationError(`${prefix}.name is required`, `${prefix}.name`);
  }

  if (!obj.resource || typeof obj.resource !== "string") {
    throw new PolicyValidationError(`${prefix}.resource is required`, `${prefix}.resource`);
  }

  if (!obj.action || typeof obj.action !== "string") {
    throw new PolicyValidationError(`${prefix}.action is required`, `${prefix}.action`);
  }

  if (!obj.expected || !VALID_EXPECTATIONS.has(obj.expected as string)) {
    throw new PolicyValidationError(
      `${prefix}.expected must be one of: ${[...VALID_EXPECTATIONS].join(", ")}`,
      `${prefix}.expected`,
      obj.expected,
    );
  }

  if (!obj.context || typeof obj.context !== "object") {
    throw new PolicyValidationError(`${prefix}.context is required and must be an object`, `${prefix}.context`);
  }

  return {
    name: obj.name as string,
    resource: obj.resource as string,
    action: obj.action as string,
    context: obj.context as Record<string, unknown>,
    expected: obj.expected as PolicyTestCase["expected"],
    expectedStatementId: typeof obj.expectedStatementId === "string" ? obj.expectedStatementId : undefined,
    description: typeof obj.description === "string" ? obj.description : undefined,
  };
}

// ─── Content Hashing ──────────────────────────────────────────────────

/**
 * Compute SHA-256 content hash for a PolicyDocument.
 * Uses canonical JSON serialization for deterministic hashing.
 */
export function computeContentHash(document: PolicyDocument): string {
  const canonical = JSON.stringify(document, Object.keys(document).sort(), 2);
  return createHash("sha256").update(canonical).digest("hex");
}

/**
 * Serialize a PolicyDocument back to YAML.
 */
export function documentToYaml(document: PolicyDocument): string {
  const raw = {
    apiVersion: document.apiVersion,
    kind: document.kind,
    metadata: {
      id: document.metadata.id,
      name: document.metadata.name,
      version: document.metadata.version,
      description: document.metadata.description,
      ...(document.metadata.compliance ? {
        compliance: document.metadata.compliance.reduce(
          (acc, c) => ({ ...acc, [c.standard]: c.sections.join(", ") }),
          {} as Record<string, string>,
        ),
      } : {}),
      ...(document.metadata.labels ? { labels: document.metadata.labels } : {}),
      ...(document.metadata.author ? { author: document.metadata.author } : {}),
    },
    statements: document.statements.map((s) => ({
      id: s.id,
      effect: s.effect,
      resource: s.resource,
      action: s.action,
      ...(s.conditions ? { conditions: s.conditions.map((c) => ({
        field: c.field,
        operator: c.operator,
        value: c.value,
        ...(c.description ? { description: c.description } : {}),
      }))} : {}),
      priority: s.priority,
      ...(s.description ? { description: s.description } : {}),
      ...(s.requiredRole ? { requiredRole: s.requiredRole } : {}),
      ...(s.tags ? { tags: s.tags } : {}),
    })),
    ...(document.tests ? {
      tests: document.tests.map((t) => ({
        name: t.name,
        resource: t.resource,
        action: t.action,
        context: t.context,
        expected: t.expected,
        ...(t.expectedStatementId ? { expectedStatementId: t.expectedStatementId } : {}),
      })),
    } : {}),
  };

  return yaml.dump(raw, {
    indent: 2,
    lineWidth: 120,
    noRefs: true,
    sortKeys: true,
    quotingType: '"',
  });
}
