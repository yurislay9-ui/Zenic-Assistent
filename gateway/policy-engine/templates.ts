// ─── Zenic-Agents v3 — Policy Template Engine ─────────────────────────
// Phase 4: Declarative Versioned Policy Engine — Template System
//
// Generates policy documents from parameterized templates with variable
// substitution, parameter validation, and constraint enforcement.
//
// Design Patterns:
//   - Builder: PolicyDocumentBuilder constructs PolicyDocument from template + params
//   - Interpreter: VariableSubstitutionInterpreter resolves {{variable}} placeholders
//   - Strategy: ParameterTypeValidator strategies per TemplateParameterType
//   - Validator: ConstraintValidator enforces cross-parameter constraint rules

import { createHash } from "crypto";
import { db } from "@/lib/db";
import { computeContentHash } from "./yaml-loader";

import type {
  PolicyDocument,
  PolicyStatement,
  PolicyCondition,
  PolicyEffectV2,
  ConditionOperator,
} from "./types";
import {
  POLICY_API_VERSION,
  POLICY_KIND,
} from "./types";

import type {
  PolicyTemplate,
  TemplateMetadata,
  TemplateParameter,
  PolicyDocumentTemplate,
  StatementTemplate,
  ConditionTemplate,
  TestCaseTemplate,
  TemplateConstraint,
  TemplateInstantiationRequest,
  TemplateInstantiationResult,
} from "./types-v2";
import {
  TEMPLATE_API_VERSION,
  TEMPLATE_KIND,
  TemplateParameterType,
  TemplateConstraintType,
} from "./types-v2";

// ─── Validation Errors ────────────────────────────────────────────────

export class TemplateValidationError extends Error {
  constructor(
    message: string,
    public readonly field: string,
    public readonly value?: unknown,
  ) {
    super(`Template validation error at "${field}": ${message}`);
    this.name = "TemplateValidationError";
  }
}

export class TemplateInstantiationError extends Error {
  constructor(
    message: string,
    public readonly templateId?: string,
  ) {
    super(`Template instantiation error${templateId ? ` for "${templateId}"` : ""}: ${message}`);
    this.name = "TemplateInstantiationError";
  }
}

// ─── Variable Substitution Interpreter ─────────────────────────────────

/** Placeholder pattern: {{variableName}} */
const PLACEHOLDER_REGEX = /\{\{(\w+)\}\}/g;

/**
 * Substitute all {{variableName}} placeholders in a string with resolved values.
 * Uses the Interpreter pattern: interprets placeholder expressions and replaces
 * them with the string representation of their resolved values.
 */
function substituteVariables(
  template: string,
  resolvedParams: Record<string, unknown>,
): string {
  return template.replace(PLACEHOLDER_REGEX, (match, varName: string) => {
    if (varName in resolvedParams) {
      const value = resolvedParams[varName];
      return valueToString(value);
    }
    // Unresolved variable — leave placeholder as-is
    return match;
  });
}

/**
 * Convert a parameter value to its string representation for substitution.
 */
function valueToString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return JSON.stringify(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Check if a string contains any unresolved {{variable}} placeholders.
 */
function hasUnresolvedVariables(str: string): string[] {
  const unresolved: string[] = [];
  let match: RegExpExecArray | null;
  const regex = new RegExp(PLACEHOLDER_REGEX.source, "g");
  while ((match = regex.exec(str)) !== null) {
    unresolved.push(match[1]!);
  }
  return unresolved;
}

/**
 * Recursively substitute variables in all string values within an object.
 * Returns a new object with substituted values.
 */
function substituteDeep<T>(obj: T, resolvedParams: Record<string, unknown>): T {
  if (typeof obj === "string") {
    return substituteVariables(obj, resolvedParams) as T;
  }
  if (Array.isArray(obj)) {
    return obj.map((item) => substituteDeep(item, resolvedParams)) as T;
  }
  if (obj !== null && typeof obj === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[key] = substituteDeep(value, resolvedParams);
    }
    return result as T;
  }
  return obj;
}

// ─── Parameter Type Validation Strategies ──────────────────────────────

/** Validation result for a single parameter */
interface ParameterValidationResult {
  valid: boolean;
  error?: string;
}

/** Strategy map for parameter type validation */
const PARAMETER_TYPE_VALIDATORS: Record<TemplateParameterType, (value: unknown, param: TemplateParameter) => ParameterValidationResult> = {
  [TemplateParameterType.STRING]: (value, param) => {
    if (typeof value !== "string") {
      return { valid: false, error: `Parameter "${param.name}" must be a string, got ${typeof value}` };
    }
    if (param.validationRegex) {
      try {
        const regex = new RegExp(param.validationRegex);
        if (!regex.test(value)) {
          return { valid: false, error: `Parameter "${param.name}" value "${value}" does not match regex "${param.validationRegex}"` };
        }
      } catch {
        return { valid: false, error: `Parameter "${param.name}" has invalid validationRegex "${param.validationRegex}"` };
      }
    }
    return { valid: true };
  },

  [TemplateParameterType.NUMBER]: (value, param) => {
    if (typeof value !== "number" || isNaN(value)) {
      return { valid: false, error: `Parameter "${param.name}" must be a number, got ${typeof value}` };
    }
    if (param.minValue !== undefined && value < param.minValue) {
      return { valid: false, error: `Parameter "${param.name}" value ${value} is below minimum ${param.minValue}` };
    }
    if (param.maxValue !== undefined && value > param.maxValue) {
      return { valid: false, error: `Parameter "${param.name}" value ${value} exceeds maximum ${param.maxValue}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.BOOLEAN]: (value, param) => {
    if (typeof value !== "boolean") {
      return { valid: false, error: `Parameter "${param.name}" must be a boolean, got ${typeof value}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.ENUM]: (value, param) => {
    if (!param.allowedValues || param.allowedValues.length === 0) {
      return { valid: false, error: `Parameter "${param.name}" has no allowedValues defined for enum type` };
    }
    if (!param.allowedValues.includes(value)) {
      return { valid: false, error: `Parameter "${param.name}" value "${String(value)}" is not in allowed values: [${param.allowedValues.map(String).join(", ")}]` };
    }
    return { valid: true };
  },

  [TemplateParameterType.ARRAY]: (value, param) => {
    if (!Array.isArray(value)) {
      return { valid: false, error: `Parameter "${param.name}" must be an array, got ${typeof value}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.OBJECT]: (value, param) => {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return { valid: false, error: `Parameter "${param.name}" must be an object, got ${value === null ? "null" : Array.isArray(value) ? "array" : typeof value}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.RESOURCE_PATTERN]: (value, param) => {
    if (typeof value !== "string") {
      return { valid: false, error: `Parameter "${param.name}" must be a string for resource_pattern, got ${typeof value}` };
    }
    if (/\s/.test(value)) {
      return { valid: false, error: `Parameter "${param.name}" resource_pattern "${value}" must not contain spaces` };
    }
    return { valid: true };
  },

  [TemplateParameterType.ACTION_PATTERN]: (value, param) => {
    if (typeof value !== "string") {
      return { valid: false, error: `Parameter "${param.name}" must be a string for action_pattern, got ${typeof value}` };
    }
    if (/\s/.test(value)) {
      return { valid: false, error: `Parameter "${param.name}" action_pattern "${value}" must not contain spaces` };
    }
    return { valid: true };
  },
};

/**
 * Validate a single parameter value against its type definition.
 * Uses Strategy pattern — dispatches to the appropriate type validator.
 */
function validateParameterType(
  value: unknown,
  param: TemplateParameter,
): ParameterValidationResult {
  const validator = PARAMETER_TYPE_VALIDATORS[param.type];
  if (!validator) {
    return { valid: false, error: `Unknown parameter type "${param.type}" for parameter "${param.name}"` };
  }
  return validator(value, param);
}

// ─── Constraint Validation ────────────────────────────────────────────

/** Result of constraint validation */
interface ConstraintValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Validate all constraint rules against resolved parameter values.
 * Each constraint type has its own validation logic.
 */
function validateConstraints(
  constraints: TemplateConstraint[],
  resolvedParams: Record<string, unknown>,
): ConstraintValidationResult {
  const errors: string[] = [];

  for (const constraint of constraints) {
    switch (constraint.type) {
      case TemplateConstraintType.MUTUALLY_EXCLUSIVE: {
        const params = constraint.parameters.parameters as string[];
        if (!Array.isArray(params) || params.length < 2) {
          errors.push(`Constraint "${constraint.name}": mutually_exclusive requires at least 2 parameters`);
          break;
        }
        const param0 = params[0]!;
        const param1 = params[1]!;
        const hasParam0 = param0 in resolvedParams && resolvedParams[param0] !== undefined && resolvedParams[param0] !== null;
        const hasParam1 = param1 in resolvedParams && resolvedParams[param1] !== undefined && resolvedParams[param1] !== null;
        if (hasParam0 && hasParam1) {
          errors.push(constraint.errorMessage || `Parameters "${param0}" and "${param1}" are mutually exclusive`);
        }
        break;
      }

      case TemplateConstraintType.REQUIRES: {
        const params = constraint.parameters.parameters as string[];
        if (!Array.isArray(params) || params.length < 2) {
          errors.push(`Constraint "${constraint.name}": requires constraint needs at least 2 parameters`);
          break;
        }
        const param0 = params[0]!;
        const param1 = params[1]!;
        const hasParam0 = param0 in resolvedParams && resolvedParams[param0] !== undefined && resolvedParams[param0] !== null;
        const hasParam1 = param1 in resolvedParams && resolvedParams[param1] !== undefined && resolvedParams[param1] !== null;
        if (hasParam0 && !hasParam1) {
          errors.push(constraint.errorMessage || `Parameter "${param0}" requires "${param1}" to also be set`);
        }
        break;
      }

      case TemplateConstraintType.RANGE_CONSTRAINT: {
        const paramName = constraint.parameters.parameter as string;
        const min = constraint.parameters.min as number | undefined;
        const max = constraint.parameters.max as number | undefined;
        const value = resolvedParams[paramName];

        if (value !== undefined && value !== null && typeof value === "number") {
          if (min !== undefined && value < min) {
            errors.push(constraint.errorMessage || `Parameter "${paramName}" value ${value} is below minimum ${min}`);
          }
          if (max !== undefined && value > max) {
            errors.push(constraint.errorMessage || `Parameter "${paramName}" value ${value} exceeds maximum ${max}`);
          }
        }
        break;
      }

      case TemplateConstraintType.REGEX_CONSTRAINT: {
        const paramName = constraint.parameters.parameter as string;
        const pattern = constraint.parameters.regex as string;
        const value = resolvedParams[paramName];

        if (value !== undefined && value !== null && typeof value === "string") {
          try {
            const regex = new RegExp(pattern);
            if (!regex.test(value)) {
              errors.push(constraint.errorMessage || `Parameter "${paramName}" value "${value}" does not match regex "${pattern}"`);
            }
          } catch {
            errors.push(`Constraint "${constraint.name}": invalid regex pattern "${pattern}"`);
          }
        }
        break;
      }

      case TemplateConstraintType.CUSTOM_EXPRESSION: {
        const expression = constraint.parameters.expression as string;
        if (typeof expression !== "string") {
          errors.push(`Constraint "${constraint.name}": custom_expression requires an expression string`);
          break;
        }
        const result = evaluateCustomExpression(expression, resolvedParams);
        if (!result) {
          errors.push(constraint.errorMessage || `Custom expression "${expression}" evaluated to false`);
        }
        break;
      }

      default:
        errors.push(`Unknown constraint type "${constraint.type}" on constraint "${constraint.name}"`);
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Evaluate a simple custom boolean expression.
 * Supports basic comparisons: param1 == "value", param1 != "value",
 * param1 > 10, param1 < 10, param1 >= 10, param1 <= 10
 * AND logical operators: expr1 && expr2
 */
function evaluateCustomExpression(
  expression: string,
  resolvedParams: Record<string, unknown>,
): boolean {
  // Split on && for AND logic
  const parts = expression.split("&&").map((s) => s.trim());

  return parts.every((part) => {
    // Try comparison operators (order matters: >= before >, <= before <)
    const compMatch = part.match(/^(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)$/);
    if (!compMatch) return false;

    const [, paramName, operator, rawValue] = compMatch;
    const paramValue = resolvedParams[paramName!];

    // Parse the comparison value
    let compValue: unknown = rawValue!.trim();
    const trimmed = rawValue!.trim();

    // Try number
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
      compValue = parseFloat(trimmed);
    }
    // Try boolean
    else if (trimmed === "true") {
      compValue = true;
    } else if (trimmed === "false") {
      compValue = false;
    }
    // Try quoted string
    else if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
      compValue = trimmed.slice(1, -1);
    }

    switch (operator) {
      case "==": return paramValue == compValue;
      case "!=": return paramValue != compValue;
      case ">": return typeof paramValue === "number" && typeof compValue === "number" && paramValue > compValue;
      case "<": return typeof paramValue === "number" && typeof compValue === "number" && paramValue < compValue;
      case ">=": return typeof paramValue === "number" && typeof compValue === "number" && paramValue >= compValue;
      case "<=": return typeof paramValue === "number" && typeof compValue === "number" && paramValue <= compValue;
      default: return false;
    }
  });
}

// ─── Template Structure Validation ────────────────────────────────────

const VALID_PARAMETER_TYPES: ReadonlySet<string> = new Set<string>([
  TemplateParameterType.STRING,
  TemplateParameterType.NUMBER,
  TemplateParameterType.BOOLEAN,
  TemplateParameterType.ENUM,
  TemplateParameterType.ARRAY,
  TemplateParameterType.OBJECT,
  TemplateParameterType.RESOURCE_PATTERN,
  TemplateParameterType.ACTION_PATTERN,
]);

const VALID_CONSTRAINT_TYPES: ReadonlySet<string> = new Set<string>([
  TemplateConstraintType.MUTUALLY_EXCLUSIVE,
  TemplateConstraintType.REQUIRES,
  TemplateConstraintType.RANGE_CONSTRAINT,
  TemplateConstraintType.REGEX_CONSTRAINT,
  TemplateConstraintType.CUSTOM_EXPRESSION,
]);

const VALID_EFFECTS: ReadonlySet<string> = new Set(["allow", "deny", "conditional"]);

/**
 * Validate the structure of a PolicyTemplate object.
 * Checks: apiVersion, kind, metadata, parameters, documentTemplate, constraints.
 * Returns an array of error strings (empty = valid).
 */
function validateTemplateStructure(template: PolicyTemplate): string[] {
  const errors: string[] = [];

  // apiVersion
  if (template.apiVersion !== TEMPLATE_API_VERSION) {
    errors.push(`Invalid apiVersion "${template.apiVersion}". Expected "${TEMPLATE_API_VERSION}"`);
  }

  // kind
  if (template.kind !== TEMPLATE_KIND) {
    errors.push(`Invalid kind "${template.kind}". Expected "${TEMPLATE_KIND}"`);
  }

  // metadata
  if (!template.metadata) {
    errors.push("metadata is required");
  } else {
    if (!template.metadata.id || typeof template.metadata.id !== "string") {
      errors.push("metadata.id is required and must be a string");
    }
    if (!template.metadata.name || typeof template.metadata.name !== "string") {
      errors.push("metadata.name is required and must be a string");
    }
    if (!template.metadata.version || typeof template.metadata.version !== "string") {
      errors.push("metadata.version is required and must be a string");
    }
    if (!template.metadata.description || typeof template.metadata.description !== "string") {
      errors.push("metadata.description is required and must be a string");
    }
    if (!template.metadata.category || typeof template.metadata.category !== "string") {
      errors.push("metadata.category is required and must be a string");
    }
    // Validate semver
    if (template.metadata.version && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/.test(template.metadata.version)) {
      errors.push(`Invalid semver format: "${template.metadata.version}"`);
    }
  }

  // parameters
  if (!Array.isArray(template.parameters)) {
    errors.push("parameters must be an array");
  } else {
    const paramNames = new Set<string>();
    for (let i = 0; i < template.parameters.length; i++) {
      const param = template.parameters[i]!;
      const prefix = `parameters[${i}]`;

      if (!param.name || typeof param.name !== "string") {
        errors.push(`${prefix}.name is required and must be a string`);
      } else {
        if (paramNames.has(param.name)) {
          errors.push(`${prefix}.name "${param.name}" is duplicated — parameter names must be unique`);
        }
        paramNames.add(param.name);
      }

      if (!param.displayName || typeof param.displayName !== "string") {
        errors.push(`${prefix}.displayName is required`);
      }

      if (!param.description || typeof param.description !== "string") {
        errors.push(`${prefix}.description is required`);
      }

      if (!param.type || !VALID_PARAMETER_TYPES.has(param.type)) {
        errors.push(`${prefix}.type must be one of: ${[...VALID_PARAMETER_TYPES].join(", ")}`);
      }

      if (param.type === TemplateParameterType.ENUM && (!param.allowedValues || param.allowedValues.length === 0)) {
        errors.push(`${prefix}.allowedValues is required for ENUM type parameter "${param.name}"`);
      }

      if (typeof param.required !== "boolean") {
        errors.push(`${prefix}.required must be a boolean`);
      }
    }
  }

  // documentTemplate
  if (!template.documentTemplate) {
    errors.push("documentTemplate is required");
  } else {
    const doc = template.documentTemplate;
    if (!doc.name || typeof doc.name !== "string") {
      errors.push("documentTemplate.name is required and must be a string");
    }
    if (!doc.description || typeof doc.description !== "string") {
      errors.push("documentTemplate.description is required and must be a string");
    }
    if (!Array.isArray(doc.statements) || doc.statements.length === 0) {
      errors.push("documentTemplate.statements must be a non-empty array");
    } else {
      for (let i = 0; i < doc.statements.length; i++) {
        const stmt = doc.statements[i]!;
        const prefix = `documentTemplate.statements[${i}]`;

        if (!stmt.id || typeof stmt.id !== "string") {
          errors.push(`${prefix}.id is required`);
        }
        if (!stmt.effect || !VALID_EFFECTS.has(stmt.effect)) {
          errors.push(`${prefix}.effect must be one of: ${[...VALID_EFFECTS].join(", ")}`);
        }
        if (!stmt.resource || typeof stmt.resource !== "string") {
          errors.push(`${prefix}.resource is required`);
        }
        if (!stmt.action || typeof stmt.action !== "string") {
          errors.push(`${prefix}.action is required`);
        }
      }
    }
  }

  // constraints (optional)
  if (template.constraints && Array.isArray(template.constraints)) {
    for (let i = 0; i < template.constraints.length; i++) {
      const constraint = template.constraints[i]!;
      const prefix = `constraints[${i}]`;

      if (!constraint.name || typeof constraint.name !== "string") {
        errors.push(`${prefix}.name is required`);
      }
      if (!constraint.type || !VALID_CONSTRAINT_TYPES.has(constraint.type)) {
        errors.push(`${prefix}.type must be one of: ${[...VALID_CONSTRAINT_TYPES].join(", ")}`);
      }
      if (!constraint.parameters || typeof constraint.parameters !== "object") {
        errors.push(`${prefix}.parameters is required and must be an object`);
      }
      if (!constraint.errorMessage || typeof constraint.errorMessage !== "string") {
        errors.push(`${prefix}.errorMessage is required`);
      }
    }
  }

  return errors;
}

/**
 * Compute a SHA-256 content hash for a PolicyTemplate.
 * Uses canonical JSON serialization for deterministic hashing.
 */
function computeTemplateContentHash(template: PolicyTemplate): string {
  const canonical = JSON.stringify(template, Object.keys(template).sort(), 2);
  return createHash("sha256").update(canonical).digest("hex");
}

// ─── Policy Document Builder ──────────────────────────────────────────

/**
 * Builder for constructing a PolicyDocument from a template and resolved parameters.
 * Applies variable substitution across all template fields using the Interpreter pattern.
 */
class PolicyDocumentBuilder {
  private documentTemplate: PolicyDocumentTemplate;
  private resolvedParams: Record<string, unknown>;
  private templateMetadata: TemplateMetadata;

  constructor(
    documentTemplate: PolicyDocumentTemplate,
    resolvedParams: Record<string, unknown>,
    templateMetadata: TemplateMetadata,
  ) {
    this.documentTemplate = documentTemplate;
    this.resolvedParams = resolvedParams;
    this.templateMetadata = templateMetadata;
  }

  /**
   * Build a complete PolicyDocument from the template.
   */
  build(): PolicyDocument {
    // Substitute metadata
    const policyName = substituteVariables(this.documentTemplate.name, this.resolvedParams);
    const policyDescription = substituteVariables(this.documentTemplate.description, this.resolvedParams);

    // Build statements
    const statements = this.documentTemplate.statements.map((stmt) =>
      this.buildStatement(stmt),
    );

    // Build tests (optional)
    const tests = this.documentTemplate.tests
      ? this.documentTemplate.tests.map((tc) => this.buildTestCase(tc))
      : undefined;

    // Build compliance (substitute in standard names if needed)
    const compliance = this.documentTemplate.compliance
      ? substituteDeep(this.documentTemplate.compliance, this.resolvedParams)
      : undefined;

    // Build labels
    const labels = this.documentTemplate.labels
      ? substituteDeep(this.documentTemplate.labels, this.resolvedParams)
      : undefined;

    return {
      apiVersion: POLICY_API_VERSION,
      kind: POLICY_KIND,
      metadata: {
        id: this.templateMetadata.id,
        name: policyName,
        version: this.templateMetadata.version,
        description: policyDescription,
        compliance,
        labels,
        author: this.templateMetadata.author,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      statements,
      tests,
    };
  }

  /**
   * Build a single PolicyStatement from a StatementTemplate.
   */
  private buildStatement(template: StatementTemplate): PolicyStatement {
    const id = substituteVariables(template.id, this.resolvedParams);
    const effect = substituteVariables(template.effect, this.resolvedParams) as PolicyEffectV2;
    const resource = substituteVariables(template.resource, this.resolvedParams);
    const action = substituteVariables(template.action, this.resolvedParams);
    const description = template.description
      ? substituteVariables(template.description, this.resolvedParams)
      : undefined;
    const requiredRole = template.requiredRole
      ? substituteVariables(template.requiredRole, this.resolvedParams)
      : undefined;
    const tags = template.tags
      ? template.tags.map((t) => substituteVariables(t, this.resolvedParams))
      : undefined;

    // Resolve priority — can be a number or a string template
    let priority: number;
    if (typeof template.priority === "number") {
      priority = template.priority;
    } else {
      const resolved = substituteVariables(template.priority, this.resolvedParams);
      const parsed = parseInt(resolved, 10);
      priority = isNaN(parsed) ? 0 : parsed;
    }

    // Build conditions
    const conditions = template.conditions
      ? template.conditions.map((ct) => this.buildCondition(ct))
      : undefined;

    return {
      id,
      effect,
      resource,
      action,
      conditions,
      priority,
      description,
      requiredRole,
      tags,
    };
  }

  /**
   * Build a single PolicyCondition from a ConditionTemplate.
   */
  private buildCondition(template: ConditionTemplate): PolicyCondition {
    const field = substituteVariables(template.field, this.resolvedParams);
    const valueStr = substituteVariables(template.value, this.resolvedParams);
    const description = template.description
      ? substituteVariables(template.description, this.resolvedParams)
      : undefined;

    // Parse value based on operator expectations
    let value: unknown = valueStr;
    // Try to parse as number
    if (/^-?\d+(\.\d+)?$/.test(valueStr)) {
      value = parseFloat(valueStr);
    }
    // Try to parse as boolean
    else if (valueStr === "true") {
      value = true;
    } else if (valueStr === "false") {
      value = false;
    }
    // Try to parse as JSON (for arrays/objects)
    else if (valueStr.startsWith("[") || valueStr.startsWith("{")) {
      try {
        value = JSON.parse(valueStr);
      } catch {
        // Keep as string
      }
    }

    return {
      field,
      operator: template.operator as ConditionOperator,
      value,
      description,
    };
  }

  /**
   * Build a single PolicyTestCase from a TestCaseTemplate.
   */
  private buildTestCase(template: TestCaseTemplate): import("./types").PolicyTestCase {
    const name = substituteVariables(template.name, this.resolvedParams);
    const resource = substituteVariables(template.resource, this.resolvedParams);
    const action = substituteVariables(template.action, this.resolvedParams);
    const context = substituteDeep(template.context, this.resolvedParams);
    const expected = substituteVariables(template.expected, this.resolvedParams) as import("./types").PolicyTestExpectation;
    const description = template.description
      ? substituteVariables(template.description, this.resolvedParams)
      : undefined;

    return {
      name,
      resource,
      action,
      context: context as Record<string, unknown>,
      expected,
      description,
    };
  }
}

// ─── DB Record Mapping ────────────────────────────────────────────────

/** Flattened record from DB with parsed JSON fields */
export interface TemplateDbRecord {
  id: string;
  templateId: string;
  name: string;
  version: string;
  description: string;
  category: string;
  industry: string | null;
  tags: string[];
  parameters: TemplateParameter[];
  documentTemplate: PolicyDocumentTemplate;
  defaults: Record<string, unknown>;
  constraints: TemplateConstraint[];
  generatedCount: number;
  isActive: boolean;
  author: string | null;
  sourceYaml: string | null;
  contentHash: string;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * Map a Prisma PolicyTemplate record to a typed TemplateDbRecord.
 */
function mapDbToRecord(record: {
  id: string;
  templateId: string;
  name: string;
  version: string;
  description: string;
  category: string;
  industry: string | null;
  tags: string;
  parameters: string;
  documentTemplate: string;
  defaults: string;
  constraints: string;
  generatedCount: number;
  isActive: boolean;
  author: string | null;
  sourceYaml: string | null;
  contentHash: string;
  createdAt: Date;
  updatedAt: Date;
}): TemplateDbRecord {
  return {
    id: record.id,
    templateId: record.templateId,
    name: record.name,
    version: record.version,
    description: record.description,
    category: record.category,
    industry: record.industry,
    tags: JSON.parse(record.tags),
    parameters: JSON.parse(record.parameters),
    documentTemplate: JSON.parse(record.documentTemplate),
    defaults: JSON.parse(record.defaults),
    constraints: JSON.parse(record.constraints),
    generatedCount: record.generatedCount,
    isActive: record.isActive,
    author: record.author,
    sourceYaml: record.sourceYaml,
    contentHash: record.contentHash,
    createdAt: record.createdAt,
    updatedAt: record.updatedAt,
  };
}

/**
 * Reconstruct a full PolicyTemplate type from a DB record.
 */
function dbRecordToTemplate(record: TemplateDbRecord): PolicyTemplate {
  return {
    apiVersion: TEMPLATE_API_VERSION,
    kind: TEMPLATE_KIND,
    metadata: {
      id: record.templateId,
      name: record.name,
      version: record.version,
      description: record.description,
      category: record.category,
      industry: record.industry ?? undefined,
      tags: record.tags,
      author: record.author ?? undefined,
      createdAt: record.createdAt.toISOString(),
      updatedAt: record.updatedAt.toISOString(),
    },
    parameters: record.parameters,
    documentTemplate: record.documentTemplate,
    defaults: record.defaults,
    constraints: record.constraints,
    generatedCount: record.generatedCount,
  };
}

// ─── Public API Functions ─────────────────────────────────────────────

/**
 * Create a new policy template in the database.
 * Validates template structure, parameter definitions, and constraint rules.
 * Computes content hash for integrity.
 */
export async function createTemplate(
  template: PolicyTemplate,
): Promise<TemplateDbRecord> {
  // 1. Validate template structure
  const structureErrors = validateTemplateStructure(template);
  if (structureErrors.length > 0) {
    throw new TemplateValidationError(
      `Template validation failed: ${structureErrors.join("; ")}`,
      "root",
    );
  }

  // 2. Check for duplicate templateId
  const existing = await db.policyTemplate.findUnique({
    where: { templateId: template.metadata.id },
  });
  if (existing) {
    throw new TemplateValidationError(
      `Template with ID "${template.metadata.id}" already exists`,
      "metadata.id",
      template.metadata.id,
    );
  }

  // 3. Compute content hash
  const contentHash = computeTemplateContentHash(template);

  // 4. Persist to database
  try {
    const created = await db.policyTemplate.create({
      data: {
        templateId: template.metadata.id,
        name: template.metadata.name,
        version: template.metadata.version,
        description: template.metadata.description,
        category: template.metadata.category,
        industry: template.metadata.industry ?? null,
        tags: JSON.stringify(template.metadata.tags ?? []),
        parameters: JSON.stringify(template.parameters),
        documentTemplate: JSON.stringify(template.documentTemplate),
        defaults: JSON.stringify(template.defaults),
        constraints: JSON.stringify(template.constraints),
        generatedCount: 0,
        isActive: true,
        author: template.metadata.author ?? null,
        contentHash,
      },
    });

    return mapDbToRecord(created);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to create template: ${error instanceof Error ? error.message : String(error)}`,
      "root",
    );
  }
}

/**
 * Get a template by its templateId.
 */
export async function getTemplate(
  templateId: string,
): Promise<TemplateDbRecord | null> {
  try {
    const record = await db.policyTemplate.findUnique({
      where: { templateId },
    });

    if (!record) return null;
    return mapDbToRecord(record);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to get template "${templateId}": ${error instanceof Error ? error.message : String(error)}`,
      "templateId",
      templateId,
    );
  }
}

/** Options for listing templates */
export interface ListTemplatesOptions {
  /** Filter by category */
  category?: string;
  /** Filter by industry */
  industry?: string;
  /** Filter by active status */
  isActive?: boolean;
  /** Maximum number of results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

/**
 * List templates with optional filtering.
 */
export async function listTemplates(
  options?: ListTemplatesOptions,
): Promise<TemplateDbRecord[]> {
  try {
    const where: Record<string, unknown> = {};

    if (options?.category !== undefined) {
      where.category = options.category;
    }
    if (options?.industry !== undefined) {
      where.industry = options.industry;
    }
    if (options?.isActive !== undefined) {
      where.isActive = options.isActive;
    }

    const records = await db.policyTemplate.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 100,
      skip: options?.offset ?? 0,
    });

    return records.map(mapDbToRecord);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to list templates: ${error instanceof Error ? error.message : String(error)}`,
      "root",
    );
  }
}

/**
 * Instantiate a template — generate a PolicyDocument from a template with parameter substitution.
 *
 * Pipeline:
 *   1. Load template from DB
 *   2. Resolve parameters (provided → defaults → unresolved)
 *   3. Validate all required parameters have values
 *   4. Apply parameter type validation
 *   5. Validate constraint rules
 *   6. Substitute {{variable}} placeholders in documentTemplate
 *   7. Generate a complete PolicyDocument via Builder
 *   8. If autoDeploy=true → store to DeclPolicy
 *   9. Increment template's generatedCount
 *  10. Return TemplateInstantiationResult
 */
export async function instantiateTemplate(
  request: TemplateInstantiationRequest,
): Promise<TemplateInstantiationResult> {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 1. Load template from DB
  let dbRecord: TemplateDbRecord;
  try {
    const record = await getTemplate(request.templateId);
    if (!record) {
      return {
        success: false,
        errors: [`Template "${request.templateId}" not found`],
        warnings: [],
        unresolvedParameters: [],
      };
    }
    if (!record.isActive) {
      return {
        success: false,
        errors: [`Template "${request.templateId}" is not active`],
        warnings: [],
        unresolvedParameters: [],
      };
    }
    dbRecord = record;
  } catch (error) {
    return {
      success: false,
      errors: [`Failed to load template: ${error instanceof Error ? error.message : String(error)}`],
      warnings: [],
      unresolvedParameters: [],
    };
  }

  const template = dbRecordToTemplate(dbRecord);

  // 2. Resolve parameters: provided values → defaults → unresolved
  const resolvedParams: Record<string, unknown> = {};
  const unresolvedParameters: string[] = [];

  for (const param of template.parameters) {
    if (param.name in request.parameters && request.parameters[param.name] !== undefined && request.parameters[param.name] !== null) {
      // Provided value
      resolvedParams[param.name] = request.parameters[param.name];
    } else if (param.defaultValue !== undefined) {
      // Default value from template definition
      resolvedParams[param.name] = param.defaultValue;
      warnings.push(`Parameter "${param.name}" using default value: ${JSON.stringify(param.defaultValue)}`);
    } else if (template.defaults[param.name] !== undefined) {
      // Default value from defaults map
      resolvedParams[param.name] = template.defaults[param.name];
      warnings.push(`Parameter "${param.name}" using default from defaults map: ${JSON.stringify(template.defaults[param.name])}`);
    } else if (param.required) {
      // Required but no value — error
      unresolvedParameters.push(param.name);
      errors.push(`Required parameter "${param.name}" has no value`);
    }
    // Optional parameter with no value → skip (unresolved)
  }

  // Early return if required parameters are missing
  if (errors.length > 0) {
    return {
      success: false,
      errors,
      warnings,
      unresolvedParameters,
    };
  }

  // 4. Apply parameter type validation
  for (const param of template.parameters) {
    if (param.name in resolvedParams) {
      const result = validateParameterType(resolvedParams[param.name], param);
      if (!result.valid) {
        errors.push(result.error!);
      }
    }
  }

  if (errors.length > 0) {
    return {
      success: false,
      errors,
      warnings,
      unresolvedParameters,
    };
  }

  // 5. Validate constraint rules
  const constraintResult = validateConstraints(template.constraints, resolvedParams);
  if (!constraintResult.valid) {
    errors.push(...constraintResult.errors);
  }

  if (errors.length > 0) {
    return {
      success: false,
      errors,
      warnings,
      unresolvedParameters,
    };
  }

  // 6 & 7. Build PolicyDocument via Builder with variable substitution
  const builder = new PolicyDocumentBuilder(
    template.documentTemplate,
    resolvedParams,
    template.metadata,
  );
  const document = builder.build();

  // Verify no critical unresolved variables in generated document
  const docString = JSON.stringify(document);
  const remainingVars = hasUnresolvedVariables(docString);
  if (remainingVars.length > 0) {
    const uniqueVars = [...new Set(remainingVars)];
    warnings.push(`Unresolved variables remain in generated document: ${uniqueVars.join(", ")}`);
  }

  // 8. Auto-deploy if requested
  let policyId: string | undefined;
  if (request.autoDeploy) {
    try {
      const targetId = request.targetPolicyId ?? `${template.metadata.id}-${Date.now()}`;
      const contentHash = computeContentHash(document);

      // Check if policy already exists
      const existing = await db.declPolicy.findUnique({
        where: { policyId: targetId },
      });

      if (existing) {
        // Update existing policy
        await db.declPolicy.update({
          where: { policyId: targetId },
          data: {
            name: document.metadata.name,
            description: document.metadata.description,
            version: document.metadata.version,
            labels: JSON.stringify(document.metadata.labels ?? {}),
            compliance: JSON.stringify(document.metadata.compliance ?? []),
            statements: JSON.stringify(document.statements),
            tests: JSON.stringify(document.tests ?? []),
            contentHash,
            author: request.requestedBy,
          },
        });
        policyId = targetId;
      } else {
        // Create new policy
        await db.declPolicy.create({
          data: {
            policyId: targetId,
            name: document.metadata.name,
            description: document.metadata.description,
            apiVersion: POLICY_API_VERSION,
            version: document.metadata.version,
            labels: JSON.stringify(document.metadata.labels ?? {}),
            compliance: JSON.stringify(document.metadata.compliance ?? []),
            statements: JSON.stringify(document.statements),
            tests: JSON.stringify(document.tests ?? []),
            isActive: true,
            contentHash,
            author: request.requestedBy,
          },
        });
        policyId = targetId;
      }
    } catch (error) {
      errors.push(`Auto-deploy failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  // 9. Increment template's generatedCount
  try {
    await db.policyTemplate.update({
      where: { templateId: request.templateId },
      data: {
        generatedCount: { increment: 1 },
      },
    });
  } catch (error) {
    warnings.push(`Failed to increment generatedCount: ${error instanceof Error ? error.message : String(error)}`);
  }

  // 10. Return result
  return {
    success: errors.length === 0,
    document: errors.length === 0 ? document : undefined,
    errors,
    warnings,
    policyId,
    unresolvedParameters: [],
  };
}

/**
 * Update a template by templateId.
 * Only the provided fields will be updated.
 * Recomputes content hash if any content fields change.
 */
export async function updateTemplate(
  templateId: string,
  updates: Partial<PolicyTemplate>,
): Promise<TemplateDbRecord> {
  // 1. Verify template exists
  const existing = await db.policyTemplate.findUnique({
    where: { templateId },
  });

  if (!existing) {
    throw new TemplateValidationError(
      `Template "${templateId}" not found`,
      "templateId",
      templateId,
    );
  }

  // 2. Build update data
  const data: Record<string, unknown> = {};

  if (updates.metadata) {
    if (updates.metadata.name !== undefined) data.name = updates.metadata.name;
    if (updates.metadata.version !== undefined) data.version = updates.metadata.version;
    if (updates.metadata.description !== undefined) data.description = updates.metadata.description;
    if (updates.metadata.category !== undefined) data.category = updates.metadata.category;
    if (updates.metadata.industry !== undefined) data.industry = updates.metadata.industry;
    if (updates.metadata.tags !== undefined) data.tags = JSON.stringify(updates.metadata.tags);
    if (updates.metadata.author !== undefined) data.author = updates.metadata.author;
  }

  if (updates.parameters !== undefined) {
    // Validate parameter definitions if updating
    const paramNames = new Set<string>();
    for (const param of updates.parameters) {
      if (paramNames.has(param.name)) {
        throw new TemplateValidationError(
          `Duplicate parameter name "${param.name}" in update`,
          "parameters",
        );
      }
      paramNames.add(param.name);
      if (param.type && !VALID_PARAMETER_TYPES.has(param.type)) {
        throw new TemplateValidationError(
          `Invalid parameter type "${param.type}"`,
          `parameters.${param.name}.type`,
          param.type,
        );
      }
    }
    data.parameters = JSON.stringify(updates.parameters);
  }

  if (updates.documentTemplate !== undefined) {
    // Validate document template if updating
    if (!Array.isArray(updates.documentTemplate.statements) || updates.documentTemplate.statements.length === 0) {
      throw new TemplateValidationError(
        "documentTemplate.statements must be a non-empty array",
        "documentTemplate.statements",
      );
    }
    data.documentTemplate = JSON.stringify(updates.documentTemplate);
  }

  if (updates.defaults !== undefined) {
    data.defaults = JSON.stringify(updates.defaults);
  }

  if (updates.constraints !== undefined) {
    // Validate constraints if updating
    for (const constraint of updates.constraints) {
      if (constraint.type && !VALID_CONSTRAINT_TYPES.has(constraint.type)) {
        throw new TemplateValidationError(
          `Invalid constraint type "${constraint.type}"`,
          `constraints.${constraint.name}.type`,
          constraint.type,
        );
      }
    }
    data.constraints = JSON.stringify(updates.constraints);
  }

  // 3. Recompute content hash if any content fields changed
  const contentFieldsChanged = ["parameters", "documentTemplate", "defaults", "constraints", "name", "description", "category", "industry"].some(
    (field) => field in data,
  );

  if (contentFieldsChanged) {
    // Reconstruct the full template with updates for hash computation
    const existingRecord = mapDbToRecord(existing);
    const existingTemplate = dbRecordToTemplate(existingRecord);
    const mergedTemplate: PolicyTemplate = {
      ...existingTemplate,
      ...updates,
      metadata: {
        ...existingTemplate.metadata,
        ...(updates.metadata ?? {}),
      },
    };
    data.contentHash = computeTemplateContentHash(mergedTemplate);
  }

  // 4. Persist update
  try {
    const updated = await db.policyTemplate.update({
      where: { templateId },
      data,
    });

    return mapDbToRecord(updated);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to update template "${templateId}": ${error instanceof Error ? error.message : String(error)}`,
      "templateId",
      templateId,
    );
  }
}

/**
 * Delete (deactivate) a template by templateId.
 * Soft delete — sets isActive to false instead of removing the record.
 */
export async function deleteTemplate(
  templateId: string,
): Promise<TemplateDbRecord> {
  // 1. Verify template exists
  const existing = await db.policyTemplate.findUnique({
    where: { templateId },
  });

  if (!existing) {
    throw new TemplateValidationError(
      `Template "${templateId}" not found`,
      "templateId",
      templateId,
    );
  }

  // 2. Soft delete (deactivate)
  try {
    const deactivated = await db.policyTemplate.update({
      where: { templateId },
      data: { isActive: false },
    });

    return mapDbToRecord(deactivated);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to deactivate template "${templateId}": ${error instanceof Error ? error.message : String(error)}`,
      "templateId",
      templateId,
    );
  }
}
