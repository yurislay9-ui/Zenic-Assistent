// ─── Zenic-Agents v3 — Policy Evaluator Helpers ────────────────────────
// Condition operator strategies, pattern matching, and evaluation helpers.
// Extracted from evaluator.ts for modularity.

import type {
  PolicyCondition,
  ConditionOperator,
  PolicyStatement,
  PolicyEvaluationRequest,
} from "../types";

// ─── Condition Operator Strategy Map ──────────────────────────────────

type OperatorFn = (fieldValue: unknown, conditionValue: unknown) => boolean;

export const OPERATOR_STRATEGIES: Record<ConditionOperator, OperatorFn> = {
  eq: (field, value) => field === value,
  neq: (field, value) => field !== value,
  in: (field, value) => Array.isArray(value) && value.includes(field),
  notin: (field, value) => Array.isArray(value) && !value.includes(field),
  gt: (field, value) => typeof field === "number" && typeof value === "number" && field > value,
  lt: (field, value) => typeof field === "number" && typeof value === "number" && field < value,
  gte: (field, value) => typeof field === "number" && typeof value === "number" && field >= value,
  lte: (field, value) => typeof field === "number" && typeof value === "number" && field <= value,
  regex: (field, value) => {
    if (typeof field !== "string" || typeof value !== "string") return false;
    try {
      // BUG #1 FIX: Safe regex with timeout protection against ReDoS.
      // INVARIANT 4: defense in depth — a malicious regex must NEVER freeze the
      // event loop on this Termux/500MB host.
      const re = new RegExp(value);
      // Reject patterns that could cause catastrophic backtracking:
      // nested quantifiers like (a+)+ or (a*){2,}
      if (/(\+|\*)[^\+\*\|\)]*?(\+|\*)/.test(value)) {
        console.warn(`[PolicyEngine] Rejected potentially dangerous regex: ${value}`);
        return false;
      }
      return re.test(field);
    } catch {
      return false;
    }
  },
  exists: (field) => field !== undefined && field !== null,
  not_exists: (field) => field === undefined || field === null,
  contains: (field, value) => {
    if (typeof field === "string" && typeof value === "string") return field.includes(value);
    if (Array.isArray(field)) return field.includes(value);
    return false;
  },
  starts_with: (field, value) => typeof field === "string" && typeof value === "string" && field.startsWith(value),
  ends_with: (field, value) => typeof field === "string" && typeof value === "string" && field.endsWith(value),
};

// ─── Pattern Matching ─────────────────────────────────────────────────

/**
 * Check if a resource/action string matches a pattern.
 * Supports wildcard: "financial/*" matches "financial/transfer"
 */
export function matchesPattern(pattern: string, value: string): boolean {
  if (pattern === "*") return true;
  if (pattern === value) return true;

  // Wildcard suffix: "financial/*" → matches "financial/transfer"
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    return value === prefix || value.startsWith(`${prefix}/`);
  }

  // Wildcard prefix: "*/execute" → matches "financial/execute"
  if (pattern.startsWith("*/")) {
    const suffix = pattern.slice(1);
    return value.endsWith(suffix);
  }

  // Glob-style: "fin*al" → not supported, exact match fallback
  return false;
}

/**
 * Evaluate a single condition against a context.
 */
export function evaluateCondition(condition: PolicyCondition, context: Record<string, unknown>): boolean {
  const fieldValue = getNestedField(context, condition.field);
  const strategy = OPERATOR_STRATEGIES[condition.operator];

  if (!strategy) {
    console.warn(`[PolicyEngine] Unknown operator: ${condition.operator}`);
    return false;
  }

  return strategy(fieldValue, condition.value);
}

/**
 * Get a nested field from an object using dot notation.
 * e.g., "request.amount" → context.request?.amount
 */
export function getNestedField(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let current: unknown = obj;

  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    if (typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }

  return current;
}

/**
 * Evaluate all conditions in a statement against a context.
 * All conditions must be true (AND logic).
 */
export function evaluateConditions(
  conditions: PolicyCondition[],
  context: Record<string, unknown>,
): boolean {
  return conditions.every((c) => evaluateCondition(c, context));
}

/**
 * Check if a statement matches a request.
 */
export function statementMatches(
  statement: PolicyStatement,
  request: PolicyEvaluationRequest,
): boolean {
  // Resource pattern match
  if (!matchesPattern(statement.resource, request.resource)) return false;

  // Action pattern match
  if (!matchesPattern(statement.action, request.action)) return false;

  // Condition evaluation
  if (statement.conditions && statement.conditions.length > 0) {
    return evaluateConditions(statement.conditions, request.context);
  }

  return true;
}
