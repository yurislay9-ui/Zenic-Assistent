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
} from "./types";
import {
  TEMPLATE_API_VERSION,
  TEMPLATE_KIND,
  TemplateParameterType,
  TemplateConstraintType,
} from "./types";

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
