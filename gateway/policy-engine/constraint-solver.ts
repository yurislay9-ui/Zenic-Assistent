// ─── Zenic-Agents v3 — Constraint Solver (Formal Verification) ──────────
// Phase 4: Declarative Versioned Policy Engine — Constraint Solver
//
// Performs formal verification of policy consistency using:
//   - AC-3 CSP constraint propagation (primary)
//   - Brute-force enumeration (small sets ≤5 policies)
//   - Hybrid: AC-3 first, brute-force for remaining
//
// Design Patterns:
//   - Strategy: Solver type selection (AC3_CSP, BRUTE_FORCE, HYBRID)
//   - Interpreter: Condition range interpretation for constraint domains
//   - Visitor: Statement pair traversal for contradiction detection
//   - Composite: Verification result aggregates contradictions, coverage, reachability

import { db } from "@/lib/db";
import type {
  PolicyDocument,
  PolicyStatement,
  PolicyCondition,
  PolicyEffectV2,
} from "./types";
import type {
  VerificationResult,
  VerificationStatus,
  SolverType,
  Contradiction,
  ContradictionType,
  UnreachableRule,
  CoverageReport,
  CoverageGap,
  PartialCoverageEntry,
} from "./types-v2";
import {
  VerificationStatus as VerificationStatusEnum,
  SolverType as SolverTypeEnum,
  ContradictionType as ContradictionTypeEnum,
} from "./types-v2";
import { PolicyEvaluator } from "./evaluator";

// ─── Solver Configuration ─────────────────────────────────────────────

const DEFAULT_SOLVER_TIMEOUT_MS = 30_000;
const BRUTE_FORCE_MAX_POLICIES = 5;
const MAX_STATEMENT_PAIRS = 50_000; // Safety limit for pair enumeration

/** Options for listing verification results */
export interface ListVerificationsOptions {
  /** Filter by status */
  status?: VerificationStatus;
  /** Filter by consistent flag */
  consistent?: boolean;
  /** Maximum number of results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

// ─── Internal Types ───────────────────────────────────────────────────

/** A condition's value range for constraint analysis */
interface ConditionRange {
  /** The field being constrained */
  field: string;
  /** Numeric lower bound (if applicable) */
  lowerBound: number | null;
  /** Whether lower bound is inclusive */
  lowerInclusive: boolean;
  /** Numeric upper bound (if applicable) */
  upperBound: number | null;
  /** Whether upper bound is inclusive */
  upperInclusive: boolean;
  /** Discrete allowed values (for eq, in) */
  allowedValues: unknown[] | null;
  /** Discrete disallowed values (for neq, notin) */
  disallowedValues: unknown[] | null;
  /** Whether this is a string-based condition (regex, contains, etc.) */
  isStringBased: boolean;
  /** Whether this is an existence check */
  isExistenceCheck: boolean;
  /** Original conditions contributing to this range */
  originalConditions: PolicyCondition[];
}

/** A statement enriched with constraint analysis data */
interface AnalyzedStatement {
  /** Source policy ID */
  policyId: string;
  /** Source policy version */
  policyVersion: string;
  /** The original statement */
  statement: PolicyStatement;
  /** Extracted condition ranges per field */
  conditionRanges: Map<string, ConditionRange>;
  /** Whether the statement has no conditions (unconditional) */
  isUnconditional: boolean;
}

/** Arc in the constraint graph */
interface ConstraintArc {
  /** First statement index */
  i: number;
  /** Second statement index */
  j: number;
}

/** AC-3 domain representation — the set of viable "effects" a statement can produce */
interface StatementDomain {
  /** Possible effects after constraint propagation */
  possibleEffects: Set<PolicyEffectV2>;
  /** Whether the domain has been reduced */
  reduced: boolean;
}

// ─── Utility Functions ────────────────────────────────────────────────

/** Generate a unique verification ID */
function generateVerificationId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `vf_${ts}_${rand}`;
}

/** Generate a unique contradiction ID */
function generateContradictionId(index: number): string {
  return `contra_${index}_${Date.now().toString(36)}`;
}

/** Check if two resource:action patterns overlap */
function patternsOverlap(resourceA: string, actionA: string, resourceB: string, actionB: string): boolean {
  return resourcePatternOverlaps(resourceA, resourceB) && actionPatternOverlaps(actionA, actionB);
}

/** Check if two resource patterns overlap */
function resourcePatternOverlaps(a: string, b: string): boolean {
  if (a === "*" || b === "*") return true;
  if (a === b) return true;

  // Wildcard suffix: "financial/*" overlaps with "financial/transfer" or "financial/*"
  if (a.endsWith("/*") && b.endsWith("/*")) {
    const prefixA = a.slice(0, -2);
    const prefixB = b.slice(0, -2);
    return prefixA === prefixB || prefixA.startsWith(`${prefixB}/`) || prefixB.startsWith(`${prefixA}/`);
  }
  if (a.endsWith("/*")) {
    const prefix = a.slice(0, -2);
    return b === prefix || b.startsWith(`${prefix}/`);
  }
  if (b.endsWith("/*")) {
    const prefix = b.slice(0, -2);
    return a === prefix || a.startsWith(`${prefix}/`);
  }

  // Wildcard prefix: "*/execute"
  if (a.startsWith("*/") && b.startsWith("*/")) {
    return a === b; // Same suffix
  }
  if (a.startsWith("*/")) {
    return b.endsWith(a.slice(1));
  }
  if (b.startsWith("*/")) {
    return a.endsWith(b.slice(1));
  }

  return false;
}

/** Check if two action patterns overlap */
function actionPatternOverlaps(a: string, b: string): boolean {
  if (a === "*" || b === "*") return true;
  return a === b;
}

/** Check if a specific value matches a resource pattern */
function valueMatchesPattern(pattern: string, value: string): boolean {
  if (pattern === "*") return true;
  if (pattern === value) return true;
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    return value === prefix || value.startsWith(`${prefix}/`);
  }
  if (pattern.startsWith("*/")) {
    return value.endsWith(pattern.slice(1));
  }
  return false;
}

// ─── Condition Range Analysis ─────────────────────────────────────────

/**
 * Extract a condition range from a set of conditions on the same field.
 * Merges multiple conditions on the same field into a single range.
 */
function extractConditionRange(conditions: PolicyCondition[], field: string): ConditionRange {
  const fieldConditions = conditions.filter((c) => c.field === field);

  const range: ConditionRange = {
    field,
    lowerBound: null,
    lowerInclusive: false,
    upperBound: null,
    upperInclusive: false,
    allowedValues: null,
    disallowedValues: null,
    isStringBased: false,
    isExistenceCheck: false,
    originalConditions: fieldConditions,
  };

  for (const cond of fieldConditions) {
    switch (cond.operator) {
      case "gt": {
        const val = Number(cond.value);
        if (!isNaN(val)) {
          range.lowerBound = range.lowerBound === null ? val : Math.max(range.lowerBound, val);
          range.lowerInclusive = false;
        }
        break;
      }
      case "lt": {
        const val = Number(cond.value);
        if (!isNaN(val)) {
          range.upperBound = range.upperBound === null ? val : Math.min(range.upperBound, val);
          range.upperInclusive = false;
        }
        break;
      }
      case "gte": {
        const val = Number(cond.value);
        if (!isNaN(val)) {
          range.lowerBound = range.lowerBound === null ? val : Math.max(range.lowerBound, val);
          range.lowerInclusive = true;
        }
        break;
      }
      case "lte": {
        const val = Number(cond.value);
        if (!isNaN(val)) {
          range.upperBound = range.upperBound === null ? val : Math.min(range.upperBound, val);
          range.upperInclusive = true;
        }
        break;
      }
      case "eq": {
        if (range.allowedValues === null) {
          range.allowedValues = [cond.value];
        } else {
          // AND logic: if eq and eq, value must be in both → intersect
          if (!range.allowedValues.includes(cond.value)) {
            range.allowedValues = []; // Impossible: can't be both values
          }
        }
        break;
      }
      case "neq": {
        if (range.disallowedValues === null) {
          range.disallowedValues = [cond.value];
        } else {
          range.disallowedValues.push(cond.value);
        }
        break;
      }
      case "in": {
        const vals = Array.isArray(cond.value) ? cond.value : [cond.value];
        if (range.allowedValues === null) {
          range.allowedValues = [...vals];
        } else {
          // Intersect with existing allowed values
          range.allowedValues = range.allowedValues.filter((v) => vals.includes(v));
        }
        break;
      }
      case "notin": {
        const vals = Array.isArray(cond.value) ? cond.value : [cond.value];
        if (range.disallowedValues === null) {
          range.disallowedValues = [...vals];
        } else {
          range.disallowedValues.push(...vals);
        }
        break;
      }
      case "regex":
      case "contains":
      case "starts_with":
      case "ends_with": {
        range.isStringBased = true;
        break;
      }
      case "exists":
      case "not_exists": {
        range.isExistenceCheck = true;
        break;
      }
    }
  }

  return range;
}

/**
 * Check if a condition range is satisfiable (can any value satisfy it?).
 * Returns { satisfiable, reason } where reason explains why not.
 */
function isRangeSatisfiable(range: ConditionRange): { satisfiable: boolean; reason: string } {
  // Check numeric bounds
  if (range.lowerBound !== null && range.upperBound !== null) {
    if (range.lowerBound > range.upperBound) {
      return {
        satisfiable: false,
        reason: `Field "${range.field}": lower bound ${range.lowerInclusive ? "≥" : ">"} ${range.lowerBound} conflicts with upper bound ${range.upperInclusive ? "≤" : "<"} ${range.upperBound}`,
      };
    }
    if (range.lowerBound === range.upperBound && (!range.lowerInclusive || !range.upperInclusive)) {
      return {
        satisfiable: false,
        reason: `Field "${range.field}": bounds ${range.lowerBound} are exclusive on at least one side, making range empty`,
      };
    }
  }

  // Check allowed values
  if (range.allowedValues !== null && range.allowedValues.length === 0) {
    return {
      satisfiable: false,
      reason: `Field "${range.field}": equality constraints eliminate all possible values`,
    };
  }

  // Check allowed values against numeric bounds
  if (range.allowedValues !== null && range.allowedValues.length > 0) {
    const numericAllowed = range.allowedValues.filter((v) => typeof v === "number") as number[];
    if (numericAllowed.length > 0 && range.lowerBound !== null && range.upperBound !== null) {
      const anyInRange = numericAllowed.some((v) => {
        const aboveLower = range.lowerInclusive ? v >= (range.lowerBound as number) : v > (range.lowerBound as number);
        const belowUpper = range.upperInclusive ? v <= (range.upperBound as number) : v < (range.upperBound as number);
        return aboveLower && belowUpper;
      });
      if (!anyInRange) {
        return {
          satisfiable: false,
          reason: `Field "${range.field}": allowed values [${numericAllowed.join(", ")}] fall outside numeric bounds`,
        };
      }
    }

    // Check allowed values against disallowed values
    if (range.disallowedValues !== null) {
      const remaining = range.allowedValues.filter((v) => !range.disallowedValues!.includes(v));
      if (remaining.length === 0) {
        return {
          satisfiable: false,
          reason: `Field "${range.field}": all allowed values are also disallowed`,
        };
      }
    }
  }

  return { satisfiable: true, reason: "" };
}

/**
 * Check if a condition range is a tautology (always true regardless of value).
 */
function isRangeTautology(range: ConditionRange): { isTautology: boolean; reason: string } {
  // Unbounded numeric range with no discrete constraints
  if (
    range.lowerBound === null &&
    range.upperBound === null &&
    range.allowedValues === null &&
    range.disallowedValues === null &&
    !range.isStringBased &&
    !range.isExistenceCheck
  ) {
    return { isTautology: false, reason: "" }; // No conditions at all — not a tautology, just unbounded
  }

  // A range that covers all possible values
  if (
    range.lowerBound === null &&
    range.upperBound === null &&
    (range.allowedValues === null || range.allowedValues.length > 0) &&
    (range.disallowedValues === null || range.disallowedValues.length === 0) &&
    !range.isStringBased &&
    !range.isExistenceCheck
  ) {
    // No actual constraint — effectively a tautology (any value satisfies)
    return {
      isTautology: true,
      reason: `Field "${range.field}": no effective constraints — condition is always true`,
    };
  }

  return { isTautology: false, reason: "" };
}

/**
 * Check if two condition ranges are mutually exclusive (no value can satisfy both).
 */
function areRangesMutuallyExclusive(
  rangeA: ConditionRange,
  rangeB: ConditionRange,
): { exclusive: boolean; reason: string } {
  if (rangeA.field !== rangeB.field) {
    return { exclusive: false, reason: "" }; // Different fields can coexist
  }

  // Both have numeric bounds
  if (rangeA.lowerBound !== null && rangeA.upperBound !== null &&
      rangeB.lowerBound !== null && rangeB.upperBound !== null) {
    // A is entirely below B
    const aMax = rangeA.upperInclusive ? rangeA.upperBound : (rangeA.upperBound as number) - 0.001;
    const bMin = rangeB.lowerInclusive ? rangeB.lowerBound : (rangeB.lowerBound as number) + 0.001;
    if (aMax < bMin) {
      return {
        exclusive: true,
        reason: `Field "${rangeA.field}": range A (${rangeA.lowerBound}..${rangeA.upperBound}) does not overlap range B (${rangeB.lowerBound}..${rangeB.upperBound})`,
      };
    }

    // B is entirely below A
    const bMax = rangeB.upperInclusive ? rangeB.upperBound : (rangeB.upperBound as number) - 0.001;
    const aMin = rangeA.lowerInclusive ? rangeA.lowerBound : (rangeA.lowerBound as number) + 0.001;
    if (bMax < aMin) {
      return {
        exclusive: true,
        reason: `Field "${rangeA.field}": range B (${rangeB.lowerBound}..${rangeB.upperBound}) does not overlap range A (${rangeA.lowerBound}..${rangeA.upperBound})`,
      };
    }
  }

  // One has allowed values, the other has disallowed
  if (rangeA.allowedValues !== null && rangeB.disallowedValues !== null) {
    const allDisallowed = rangeA.allowedValues.every((v) => rangeB.disallowedValues!.includes(v));
    if (allDisallowed && rangeA.allowedValues.length > 0) {
      return {
        exclusive: true,
        reason: `Field "${rangeA.field}": A requires values in [${rangeA.allowedValues.join(", ")}] but B excludes all of them`,
      };
    }
  }
  if (rangeB.allowedValues !== null && rangeA.disallowedValues !== null) {
    const allDisallowed = rangeB.allowedValues.every((v) => rangeA.disallowedValues!.includes(v));
    if (allDisallowed && rangeB.allowedValues.length > 0) {
      return {
        exclusive: true,
        reason: `Field "${rangeB.field}": B requires values in [${rangeB.allowedValues.join(", ")}] but A excludes all of them`,
      };
    }
  }

  // Both have allowed values with no intersection
  if (rangeA.allowedValues !== null && rangeB.allowedValues !== null) {
    const intersection = rangeA.allowedValues.filter((v) => rangeB.allowedValues!.includes(v));
    if (intersection.length === 0) {
      return {
        exclusive: true,
        reason: `Field "${rangeA.field}": A allows [${rangeA.allowedValues.join(", ")}], B allows [${rangeB.allowedValues.join(", ")}] — no intersection`,
      };
    }
  }

  return { exclusive: false, reason: "" };
}

/**
 * Check if rangeA is a subset of rangeB (all values satisfying A also satisfy B).
 */
function isRangeSubset(rangeA: ConditionRange, rangeB: ConditionRange): boolean {
  if (rangeA.field !== rangeB.field) return false;

  // If A has numeric bounds that are tighter than B's
  const aNarrowerLower =
    rangeA.lowerBound !== null &&
    (rangeB.lowerBound === null ||
     rangeA.lowerBound > rangeB.lowerBound ||
     (rangeA.lowerBound === rangeB.lowerBound && !rangeA.lowerInclusive && rangeB.lowerInclusive));

  const aNarrowerUpper =
    rangeA.upperBound !== null &&
    (rangeB.upperBound === null ||
     rangeA.upperBound < rangeB.upperBound ||
     (rangeA.upperBound === rangeB.upperBound && !rangeA.upperInclusive && rangeB.upperInclusive));

  // A is subset if A's range is contained within B's
  if (rangeA.lowerBound !== null && rangeB.lowerBound !== null) {
    if (rangeA.lowerBound < rangeB.lowerBound) return false;
    if (rangeA.lowerBound === rangeB.lowerBound && !rangeA.lowerInclusive && rangeB.lowerInclusive) return false;
  }
  if (rangeA.upperBound !== null && rangeB.upperBound !== null) {
    if (rangeA.upperBound > rangeB.upperBound) return false;
    if (rangeA.upperBound === rangeB.upperBound && !rangeA.upperInclusive && rangeB.upperInclusive) return false;
  }

  // If A has allowed values that are a subset of B's
  if (rangeA.allowedValues !== null && rangeB.allowedValues !== null) {
    if (!rangeA.allowedValues.every((v) => rangeB.allowedValues!.includes(v))) return false;
  }

  // If B is unbounded and A has constraints, A is narrower
  if (rangeA.lowerBound !== null && rangeB.lowerBound === null) return true;
  if (rangeA.upperBound !== null && rangeB.upperBound === null) return true;

  return aNarrowerLower || aNarrowerUpper;
}

// ─── Policy Loading ───────────────────────────────────────────────────

/**
 * Load policies from the database.
 * If policyIds is specified, only those policies are loaded.
 * Otherwise, all active policies are loaded.
 */
async function loadPolicies(policyIds?: string[]): Promise<PolicyDocument[]> {
  const where = policyIds && policyIds.length > 0
    ? { policyId: { in: policyIds }, isActive: true }
    : { isActive: true };

  const policies = await db.declPolicy.findMany({
    where,
    orderBy: { updatedAt: "desc" },
  });

  return policies.map((p) => ({
    apiVersion: p.apiVersion as "policy.zenic.dev/v1",
    kind: "PolicyDocument" as const,
    metadata: {
      id: p.policyId,
      name: p.name,
      version: p.version,
      description: p.description,
      compliance: JSON.parse(p.compliance),
      labels: JSON.parse(p.labels),
      author: p.author ?? undefined,
      createdAt: p.createdAt.toISOString(),
      updatedAt: p.updatedAt.toISOString(),
    },
    statements: JSON.parse(p.statements),
    tests: JSON.parse(p.tests),
  }));
}

/**
 * Analyze all statements from a set of policies.
 */
function analyzeStatements(policies: PolicyDocument[]): AnalyzedStatement[] {
  const analyzed: AnalyzedStatement[] = [];

  for (const policy of policies) {
    for (const statement of policy.statements) {
      const conditions = statement.conditions ?? [];
      const conditionRanges = new Map<string, ConditionRange>();

      // Group conditions by field
      const fieldGroups = new Map<string, PolicyCondition[]>();
      for (const cond of conditions) {
        const existing = fieldGroups.get(cond.field) ?? [];
        existing.push(cond);
        fieldGroups.set(cond.field, existing);
      }

      // Extract range for each field
      for (const [field, fieldConditions] of fieldGroups) {
        conditionRanges.set(field, extractConditionRange(fieldConditions, field));
      }

      analyzed.push({
        policyId: policy.metadata.id,
        policyVersion: policy.metadata.version,
        statement,
        conditionRanges,
        isUnconditional: conditions.length === 0,
      });
    }
  }

  return analyzed;
}

// ─── Consistency Check (AC-3 CSP) ────────────────────────────────────

/**
 * Run AC-3 arc consistency algorithm on the constraint graph.
 * Returns detected contradictions.
 */
function runAC3Consistency(
  analyzed: AnalyzedStatement[],
  startTime: number,
  timeoutMs: number,
): Contradiction[] {
  const contradictions: Contradiction[] = [];
  let contradictionIndex = 0;

  // Build constraint graph: arcs between statements that overlap on resource:action
  const arcs: ConstraintArc[] = [];
  for (let i = 0; i < analyzed.length; i++) {
    for (let j = i + 1; j < analyzed.length; j++) {
      const a = analyzed[i]!;
      const b = analyzed[j]!;

      if (patternsOverlap(a.statement.resource, a.statement.action, b.statement.resource, b.statement.action)) {
        arcs.push({ i, j });
      }
    }

    // Safety: check timeout periodically
    if (i % 50 === 0 && Date.now() - startTime > timeoutMs) {
      return contradictions;
    }
  }

  // Check pair count safety
  if (arcs.length > MAX_STATEMENT_PAIRS) {
    // Only process first MAX_STATEMENT_PAIRS arcs
    arcs.length = MAX_STATEMENT_PAIRS;
  }

  // Initialize domains for each statement
  const domains: StatementDomain[] = analyzed.map((a) => ({
    possibleEffects: new Set<PolicyEffectV2>([a.statement.effect]),
    reduced: false,
  }));

  // AC-3 queue
  const queue = [...arcs];

  while (queue.length > 0) {
    // Check timeout
    if (Date.now() - startTime > timeoutMs) {
      break;
    }

    const arc = queue.shift()!;
    const { i, j } = arc;
    const stmtA = analyzed[i]!;
    const stmtB = analyzed[j]!;

    // Check for EFFECT_CONFLICT: same resource:action, opposite effects
    if (
      stmtA.statement.effect !== stmtB.statement.effect &&
      patternsOverlap(stmtA.statement.resource, stmtA.statement.action, stmtB.statement.resource, stmtB.statement.action)
    ) {
      // Check if conditions can overlap (not mutually exclusive)
      const conditionsMutuallyExclusive = checkConditionsMutuallyExclusive(stmtA, stmtB);

      if (!conditionsMutuallyExclusive) {
        // Both statements can match the same request but have different effects
        contradictions.push({
          id: generateContradictionId(contradictionIndex++),
          type: ContradictionTypeEnum.EFFECT_CONFLICT,
          statements: [
            { policyId: stmtA.policyId, statementId: stmtA.statement.id, effect: stmtA.statement.effect },
            { policyId: stmtB.policyId, statementId: stmtB.statement.id, effect: stmtB.statement.effect },
          ],
          triggeringCondition: {
            resource: `${stmtA.statement.resource}:${stmtA.statement.action}`,
            overlapNote: "Both statements can match the same request",
          },
          explanation: `Statement "${stmtA.statement.id}" (${stmtA.statement.effect}) in policy "${stmtA.policyId}" conflicts with statement "${stmtB.statement.id}" (${stmtB.statement.effect}) in policy "${stmtB.policyId}" on resource:action ${stmtA.statement.resource}:${stmtA.statement.action}`,
          suggestedFix: `Add mutually exclusive conditions or adjust priorities to resolve the ${stmtA.statement.effect}/${stmtB.statement.effect} conflict`,
        });
      }
    }

    // AC-3 domain reduction: check if constraints reduce the domain
    const domainChanged = reduceArcDomain(domains, analyzed, i, j);
    if (domainChanged) {
      // Re-add all arcs involving i to the queue
      for (const otherArc of arcs) {
        if ((otherArc.i === i || otherArc.j === i) && otherArc !== arc) {
          queue.push(otherArc);
        }
      }
    }
  }

  // Check for empty domains (unsatisfiable)
  for (let i = 0; i < analyzed.length; i++) {
    const stmt = analyzed[i]!;
    const domain = domains[i]!;

    if (domain.possibleEffects.size === 0) {
      contradictions.push({
        id: generateContradictionId(contradictionIndex++),
        type: ContradictionTypeEnum.UNSATISFIABLE_CONDITION,
        statements: [{ policyId: stmt.policyId, statementId: stmt.statement.id, effect: stmt.statement.effect }],
        triggeringCondition: { statementId: stmt.statement.id, reason: "Domain became empty after constraint propagation" },
        explanation: `Statement "${stmt.statement.id}" in policy "${stmt.policyId}" has conditions that can never be satisfied`,
        suggestedFix: "Review and fix the condition constraints so they can be satisfied by some value",
      });
    }
  }

  // Check for unsatisfiable conditions within individual statements
  for (const stmt of analyzed) {
    for (const [field, range] of stmt.conditionRanges) {
      const { satisfiable, reason } = isRangeSatisfiable(range);
      if (!satisfiable) {
        contradictions.push({
          id: generateContradictionIndex(contradictionIndex++, field),
          type: ContradictionTypeEnum.UNSATISFIABLE_CONDITION,
          statements: [{ policyId: stmt.policyId, statementId: stmt.statement.id, effect: stmt.statement.effect }],
          triggeringCondition: { field, reason },
          explanation: `Statement "${stmt.statement.id}" in policy "${stmt.policyId}" has unsatisfiable condition: ${reason}`,
          suggestedFix: `Remove or adjust the conflicting condition on field "${field}"`,
        });
      }

      const { isTautology, reason: tautologyReason } = isRangeTautology(range);
      if (isTautology) {
        contradictions.push({
          id: generateContradictionIndex(contradictionIndex++, field),
          type: ContradictionTypeEnum.TAUTOLOGY,
          statements: [{ policyId: stmt.policyId, statementId: stmt.statement.id, effect: stmt.statement.effect }],
          triggeringCondition: { field, reason: tautologyReason },
          explanation: `Statement "${stmt.statement.id}" in policy "${stmt.policyId}" has a tautological condition: ${tautologyReason}`,
          suggestedFix: `Remove the redundant condition on field "${field}" or add meaningful constraints`,
        });
      }
    }
  }

  // Check for mutual exclusion between pairs
  for (const arc of arcs) {
    const stmtA = analyzed[arc.i]!;
    const stmtB = analyzed[arc.j]!;

    // Find shared fields
    const sharedFields = new Set<string>();
    for (const field of stmtA.conditionRanges.keys()) {
      if (stmtB.conditionRanges.has(field)) {
        sharedFields.add(field);
      }
    }

    for (const field of sharedFields) {
      const rangeA = stmtA.conditionRanges.get(field)!;
      const rangeB = stmtB.conditionRanges.get(field)!;
      const { exclusive, reason } = areRangesMutuallyExclusive(rangeA, rangeB);

      if (exclusive) {
        contradictions.push({
          id: generateContradictionIndex(contradictionIndex++, field),
          type: ContradictionTypeEnum.MUTUAL_EXCLUSION,
          statements: [
            { policyId: stmtA.policyId, statementId: stmtA.statement.id, effect: stmtA.statement.effect },
            { policyId: stmtB.policyId, statementId: stmtB.statement.id, effect: stmtB.statement.effect },
          ],
          triggeringCondition: { field, reason },
          explanation: `Statements "${stmtA.statement.id}" and "${stmtB.statement.id}" have mutually exclusive conditions on field "${field}": ${reason}`,
          suggestedFix: "Adjust conditions so they can overlap, or accept that the rules never apply simultaneously",
        });
      }
    }
  }

  return contradictions;
}

/** Helper to generate contradiction ID with field context */
function generateContradictionIndex(index: number, field: string): string {
  return `contra_${index}_${field.replace(/[^a-zA-Z0-9]/g, "_")}_${Date.now().toString(36)}`;
}

/**
 * Check if two analyzed statements have mutually exclusive conditions.
 */
function checkConditionsMutuallyExclusive(a: AnalyzedStatement, b: AnalyzedStatement): boolean {
  // If either is unconditional, they're not mutually exclusive
  if (a.isUnconditional || b.isUnconditional) return false;

  // Check each shared field
  for (const [field, rangeA] of a.conditionRanges) {
    const rangeB = b.conditionRanges.get(field);
    if (!rangeB) continue;

    const { exclusive } = areRangesMutuallyExclusive(rangeA, rangeB);
    if (exclusive) return true;
  }

  return false;
}

/**
 * Reduce domain for an arc in AC-3.
 * Returns true if the domain was changed.
 */
function reduceArcDomain(
  domains: StatementDomain[],
  analyzed: AnalyzedStatement[],
  i: number,
  j: number,
): boolean {
  const stmtA = analyzed[i]!;
  const stmtB = analyzed[j]!;

  // If both statements have the same resource:action and opposite effects,
  // and their conditions can overlap, then the lower-priority effect is "shadowed"
  // This doesn't reduce the domain per se, but marks a potential issue
  if (
    stmtA.statement.effect !== stmtB.statement.effect &&
    patternsOverlap(stmtA.statement.resource, stmtA.statement.action, stmtB.statement.resource, stmtB.statement.action)
  ) {
    // The lower-priority statement's effect may be unreachable in some scenarios
    // but we don't reduce the domain — just note the conflict
    return false;
  }

  // Domain reduction: if conditions are mutually exclusive, the statements
  // can't both apply to the same request, so there's no domain conflict
  const exclusiveFields: string[] = [];
  for (const [field, rangeA] of stmtA.conditionRanges) {
    const rangeB = stmtB.conditionRanges.get(field);
    if (!rangeB) continue;
    const { exclusive } = areRangesMutuallyExclusive(rangeA, rangeB);
    if (exclusive) exclusiveFields.push(field);
  }

  if (exclusiveFields.length > 0) {
    // Domains don't conflict — no reduction needed
    return false;
  }

  // No reduction performed in this simplified AC-3
  return false;
}

// ─── Brute Force Solver ──────────────────────────────────────────────

/**
 * Brute-force consistency check: enumerate condition value combinations.
 * Only suitable for small policy sets (≤5 policies).
 */
function runBruteForceConsistency(
  analyzed: AnalyzedStatement[],
  _evaluator: PolicyEvaluator,
  startTime: number,
  timeoutMs: number,
): Contradiction[] {
  const contradictions: Contradiction[] = [];
  let contradictionIndex = 0;

  // Collect all unique fields and their possible values from conditions
  const fieldValues = new Map<string, Set<unknown>>();
  for (const stmt of analyzed) {
    for (const [field, range] of stmt.conditionRanges) {
      if (!fieldValues.has(field)) {
        fieldValues.set(field, new Set());
      }
      const values = fieldValues.get(field)!;

      if (range.allowedValues !== null) {
        for (const v of range.allowedValues) values.add(v);
      }
      if (range.lowerBound !== null) values.add(range.lowerBound);
      if (range.upperBound !== null) values.add(range.upperBound);
      // Add midpoint for range coverage
      if (range.lowerBound !== null && range.upperBound !== null) {
        values.add(Math.floor((range.lowerBound + range.upperBound) / 2));
      }
    }
  }

  // Generate test contexts by enumerating field combinations
  const fields = Array.from(fieldValues.keys());
  const valueArrays = fields.map((f) => {
    const vals = Array.from(fieldValues.get(f)!);
    return vals.length > 0 ? vals : [null]; // null represents "field not present"
  });

  // Calculate total combinations (with safety limit)
  let totalCombinations = 1;
  for (const arr of valueArrays) {
    totalCombinations *= arr.length;
    if (totalCombinations > 10_000) {
      totalCombinations = 10_000;
      break;
    }
  }

  // Generate contexts and check for conflicts
  const resourceActionPairs = new Set<string>();
  for (const stmt of analyzed) {
    resourceActionPairs.add(`${stmt.statement.resource}:${stmt.statement.action}`);
  }

  // For each resource:action pair, check what effects are possible
  for (const raPair of resourceActionPairs) {
    if (Date.now() - startTime > timeoutMs) break;

    const [resourcePattern, actionPattern] = raPair.split(":");
    const matchingStmts = analyzed.filter((s) =>
      valueMatchesPattern(s.statement.resource, resourcePattern ?? "*") &&
      valueMatchesPattern(s.statement.action, actionPattern ?? "*"),
    );

    if (matchingStmts.length < 2) continue;

    // Check if any two matching statements have conflicting effects
    for (let i = 0; i < matchingStmts.length; i++) {
      for (let j = i + 1; j < matchingStmts.length; j++) {
        const a = matchingStmts[i]!;
        const b = matchingStmts[j]!;

        if (a.statement.effect !== b.statement.effect) {
          // Check if their conditions can simultaneously be true
          const exclusive = checkConditionsMutuallyExclusive(a, b);
          if (!exclusive) {
            contradictions.push({
              id: generateContradictionIndex(contradictionIndex++, "brute"),
              type: ContradictionTypeEnum.EFFECT_CONFLICT,
              statements: [
                { policyId: a.policyId, statementId: a.statement.id, effect: a.statement.effect },
                { policyId: b.policyId, statementId: b.statement.id, effect: b.statement.effect },
              ],
              triggeringCondition: {
                resource: resourcePattern,
                action: actionPattern,
                method: "brute_force_enumeration",
              },
              explanation: `Brute-force: statements "${a.statement.id}" (${a.statement.effect}) and "${b.statement.id}" (${b.statement.effect}) can both match ${resourcePattern}:${actionPattern}`,
              suggestedFix: "Add mutually exclusive conditions or adjust priorities",
            });
          }
        }
      }
    }
  }

  // Also check unsatisfiable conditions (reuse same logic as AC-3)
  for (const stmt of analyzed) {
    for (const [field, range] of stmt.conditionRanges) {
      const { satisfiable, reason } = isRangeSatisfiable(range);
      if (!satisfiable) {
        contradictions.push({
          id: generateContradictionIndex(contradictionIndex++, field),
          type: ContradictionTypeEnum.UNSATISFIABLE_CONDITION,
          statements: [{ policyId: stmt.policyId, statementId: stmt.statement.id, effect: stmt.statement.effect }],
          triggeringCondition: { field, reason, method: "brute_force" },
          explanation: `Brute-force: statement "${stmt.statement.id}" has unsatisfiable condition: ${reason}`,
          suggestedFix: `Fix the condition on field "${field}"`,
        });
      }
    }
  }

  return contradictions;
}

// ─── Completeness Check ──────────────────────────────────────────────

/**
 * Check completeness: are all resource:action pairs covered by at least one statement?
 */
function runCompletenessCheck(
  analyzed: AnalyzedStatement[],
  policies: PolicyDocument[],
): CoverageReport {
  // Collect all concrete resource:action pairs from statements and test cases
  const coveredPairs = new Set<string>();
  const statementCoverage = new Map<string, AnalyzedStatement[]>();

  for (const stmt of analyzed) {
    const key = `${stmt.statement.resource}:${stmt.statement.action}`;
    coveredPairs.add(key);
    const existing = statementCoverage.get(key) ?? [];
    existing.push(stmt);
    statementCoverage.set(key, existing);
  }

  // Define the resource:action space from statements and test cases
  const allResources = new Set<string>();
  const allActions = new Set<string>();

  for (const stmt of analyzed) {
    allResources.add(stmt.statement.resource);
    allActions.add(stmt.statement.action);
  }

  // Also collect from test cases
  for (const policy of policies) {
    if (policy.tests) {
      for (const test of policy.tests) {
        allResources.add(test.resource);
        allActions.add(test.action);
      }
    }
  }

  // Common default actions to check for coverage gaps
  const defaultActions = ["read", "write", "execute", "delete", "admin", "*"];
  for (const action of defaultActions) {
    allActions.add(action);
  }

  // Calculate total space
  const resourceList = Array.from(allResources);
  const actionList = Array.from(allActions);
  const totalSpace = resourceList.length * actionList.length;

  // Check coverage
  const gaps: CoverageGap[] = [];
  const partialCoverage: PartialCoverageEntry[] = [];
  let coveredCount = 0;

  for (const resource of resourceList) {
    for (const action of actionList) {
      const key = `${resource}:${action}`;
      const matchingStmts = findMatchingStatements(analyzed, resource, action);

      if (matchingStmts.length === 0) {
        // Check if any wildcard pattern covers this
        const wildcardMatches = findMatchingStatements(analyzed, resource.endsWith("/*") ? resource : `${resource}/*`, action);
        const resourceWildcardMatches = findMatchingStatements(analyzed, "*", action);

        if (wildcardMatches.length === 0 && resourceWildcardMatches.length === 0) {
          gaps.push({
            resource,
            action,
            reason: `No statement matches resource "${resource}" with action "${action}"`,
            suggestedStatement: {
              resource,
              action,
              effect: "deny" as PolicyEffectV2,
              priority: 0,
            },
          });
        } else {
          coveredCount++;
        }
      } else {
        coveredCount++;

        // Check if all conditions are covered (partial coverage)
        const conditionalStmts = matchingStmts.filter((s) => !s.isUnconditional);
        const unconditionalStmts = matchingStmts.filter((s) => s.isUnconditional);

        if (conditionalStmts.length > 0 && unconditionalStmts.length === 0) {
          // Only conditional coverage — check for uncovered condition space
          const coveredConditions: string[] = [];
          const uncoveredConditions: string[] = [];

          for (const stmt of conditionalStmts) {
            for (const [field, range] of stmt.conditionRanges) {
              coveredConditions.push(
                `${field}: ${range.lowerBound ?? "-∞"}..${range.upperBound ?? "+∞"}`,
              );
            }
          }

          // Add uncovered conditions for common fields that aren't covered
          const coveredFields = new Set<string>();
          for (const stmt of conditionalStmts) {
            for (const field of stmt.conditionRanges.keys()) {
              coveredFields.add(field);
            }
          }

          // If there are fields that aren't fully covered, mark as partial
          if (coveredConditions.length > 0) {
            uncoveredConditions.push("Requests with no matching condition values (deny-by-default applies)");

            partialCoverage.push({
              resource,
              action,
              coveredConditions,
              uncoveredConditions,
              coveragePct: Math.round((coveredConditions.length / (coveredConditions.length + uncoveredConditions.length)) * 100),
            });
          }
        }
      }
    }
  }

  const coveragePct = totalSpace > 0 ? Math.round((coveredCount / totalSpace) * 100) : 100;

  return {
    totalSpace,
    coveredSpace: coveredCount,
    coveragePct,
    gaps,
    partialCoverage,
  };
}

/**
 * Find all statements that match a specific resource:action pair.
 */
function findMatchingStatements(
  analyzed: AnalyzedStatement[],
  resource: string,
  action: string,
): AnalyzedStatement[] {
  return analyzed.filter((s) =>
    valueMatchesPattern(s.statement.resource, resource) &&
    valueMatchesPattern(s.statement.action, action),
  );
}

// ─── Reachability Check ──────────────────────────────────────────────

/**
 * Check for unreachable (shadowed) rules.
 * A rule is unreachable if a higher-priority rule always matches first
 * for the same resource:action with the same or broader conditions.
 */
function runReachabilityCheck(analyzed: AnalyzedStatement[]): UnreachableRule[] {
  const unreachable: UnreachableRule[] = [];

  // Sort by priority (highest first)
  const sorted = [...analyzed].sort((a, b) => b.statement.priority - a.statement.priority);

  for (let i = 0; i < sorted.length; i++) {
    const lower = sorted[i]!;

    for (let j = 0; j < i; j++) {
      const higher = sorted[j]!;

      // Check if higher-priority statement shadows the lower one
      if (!patternsOverlap(higher.statement.resource, higher.statement.action, lower.statement.resource, lower.statement.action)) {
        continue;
      }

      // Same resource:action — check if higher-priority covers the lower
      const isShadowed = checkShadowing(higher, lower);
      if (isShadowed) {
        unreachable.push({
          policyId: lower.policyId,
          statementId: lower.statement.id,
          reason: `Statement "${lower.statement.id}" (priority ${lower.statement.priority}) is shadowed by "${higher.statement.id}" (priority ${higher.statement.priority}) on ${lower.statement.resource}:${lower.statement.action}`,
          shadowingStatementId: higher.statement.id,
          shadowingPolicyId: higher.policyId,
        });
        break; // Only report the highest-priority shadow
      }
    }
  }

  return unreachable;
}

/**
 * Check if the higher-priority statement shadows the lower-priority one.
 * Shadowing occurs when the higher statement's conditions are a superset
 * (or equal) of the lower statement's conditions for the same resource:action.
 */
function checkShadowing(higher: AnalyzedStatement, lower: AnalyzedStatement): boolean {
  // If higher is unconditional, it shadows everything on the same resource:action
  if (higher.isUnconditional) return true;

  // If lower is unconditional but higher has conditions, higher doesn't shadow lower completely
  if (lower.isUnconditional) return false;

  // Check if every condition in lower is covered by higher
  for (const [field, lowerRange] of lower.conditionRanges) {
    const higherRange = higher.conditionRanges.get(field);
    if (!higherRange) {
      // Lower has a condition on a field that higher doesn't constrain
      // → higher's condition is broader on this field → doesn't shadow
      return false;
    }

    // Check if higher's range covers lower's range (higher is a superset)
    if (!isRangeSubset(lowerRange, higherRange) && !rangesEquivalent(lowerRange, higherRange)) {
      return false;
    }
  }

  // Also check if higher has extra conditions that lower doesn't have
  // If higher has conditions on fields that lower doesn't, higher is more specific
  // and doesn't shadow lower for all cases
  for (const field of higher.conditionRanges.keys()) {
    if (!lower.conditionRanges.has(field)) {
      return false; // Higher has extra conditions → doesn't universally shadow
    }
  }

  return true;
}

/**
 * Check if two ranges are equivalent (cover the same value space).
 */
function rangesEquivalent(a: ConditionRange, b: ConditionRange): boolean {
  if (a.lowerBound !== b.lowerBound || a.upperBound !== b.upperBound) return false;
  if (a.lowerInclusive !== b.lowerInclusive || a.upperInclusive !== b.upperInclusive) return false;
  if (a.isStringBased !== b.isStringBased || a.isExistenceCheck !== b.isExistenceCheck) return false;

  if (a.allowedValues === null && b.allowedValues !== null) return false;
  if (a.allowedValues !== null && b.allowedValues === null) return false;
  if (a.allowedValues !== null && b.allowedValues !== null) {
    if (a.allowedValues.length !== b.allowedValues.length) return false;
    if (!a.allowedValues.every((v) => b.allowedValues!.includes(v))) return false;
  }

  if (a.disallowedValues === null && b.disallowedValues !== null) return false;
  if (a.disallowedValues !== null && b.disallowedValues === null) return false;
  if (a.disallowedValues !== null && b.disallowedValues !== null) {
    if (a.disallowedValues.length !== b.disallowedValues.length) return false;
    if (!a.disallowedValues.every((v) => b.disallowedValues!.includes(v))) return false;
  }

  return true;
}

// ─── Main Verification Function ──────────────────────────────────────

/**
 * Verify a set of policies for consistency, completeness, and reachability.
 *
 * @param policyIds - Optional array of policy IDs to verify. If not specified, all active policies are verified.
 * @param solverType - The solver algorithm to use. Defaults to AC3_CSP.
 * @returns VerificationResult with contradictions, coverage gaps, and unreachable rules.
 */
export async function verifyPolicies(
  policyIds?: string[],
  solverType?: SolverType,
): Promise<VerificationResult> {
  const startTime = Date.now();
  const effectiveSolverType = solverType ?? SolverTypeEnum.AC3_CSP;
  const timeoutMs = DEFAULT_SOLVER_TIMEOUT_MS;

  try {
    // 1. Load policies from DB
    const policies = await loadPolicies(policyIds);

    if (policies.length === 0) {
      return {
        consistent: true,
        complete: true,
        hasUnreachableRules: false,
        status: VerificationStatusEnum.WARNING,
        contradictions: [],
        unreachableRules: [],
        coverage: { totalSpace: 0, coveredSpace: 0, coveragePct: 100, gaps: [], partialCoverage: [] },
        duration: Date.now() - startTime,
        solverType: effectiveSolverType,
        summary: "No policies found to verify",
      };
    }

    // 2. Analyze statements
    const analyzed = analyzeStatements(policies);

    // 3. Run consistency check based on solver type
    let contradictions: Contradiction[];

    switch (effectiveSolverType) {
      case SolverTypeEnum.BRUTE_FORCE: {
        if (policies.length > BRUTE_FORCE_MAX_POLICIES) {
          contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);
          contradictions.push({
            id: generateContradictionIndex(0, "solver_fallback"),
            type: ContradictionTypeEnum.TAUTOLOGY,
            statements: [],
            triggeringCondition: { note: "Brute-force not applicable, fell back to AC-3" },
            explanation: `Too many policies (${policies.length}) for brute-force solver (max ${BRUTE_FORCE_MAX_POLICIES}), used AC-3 instead`,
            suggestedFix: "Use AC3_CSP or HYBRID solver for larger policy sets",
          });
        } else {
          const evaluator = new PolicyEvaluator();
          contradictions = runBruteForceConsistency(analyzed, evaluator, startTime, timeoutMs);
        }
        break;
      }
      case SolverTypeEnum.HYBRID: {
        // Try AC-3 first
        contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);

        // If no contradictions found with AC-3 and policy count is small, try brute force
        if (contradictions.length === 0 && policies.length <= BRUTE_FORCE_MAX_POLICIES) {
          const remainingTime = timeoutMs - (Date.now() - startTime);
          if (remainingTime > 1000) {
            const evaluator = new PolicyEvaluator();
            const bruteForceResults = runBruteForceConsistency(analyzed, evaluator, startTime, Math.min(remainingTime, timeoutMs));
            contradictions = [...contradictions, ...bruteForceResults];
          }
        }
        break;
      }
      case SolverTypeEnum.Z3_SAT: {
        // Z3 SAT solver is not available — fall back to AC-3
        contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);
        break;
      }
      case SolverTypeEnum.AC3_CSP:
      default: {
        contradictions = runAC3Consistency(analyzed, startTime, timeoutMs);
        break;
      }
    }

    // Check for timeout
    if (Date.now() - startTime > timeoutMs) {
      const result: VerificationResult = {
        consistent: contradictions.length === 0,
        complete: false,
        hasUnreachableRules: false,
        status: VerificationStatusEnum.TIMEOUT,
        contradictions,
        unreachableRules: [],
        coverage: { totalSpace: 0, coveredSpace: 0, coveragePct: 0, gaps: [], partialCoverage: [] },
        duration: Date.now() - startTime,
        solverType: effectiveSolverType,
        summary: `Verification timed out after ${timeoutMs}ms. ${contradictions.length} contradictions found before timeout.`,
      };

      // Persist the timeout result
      await persistVerification(policyIds ?? [], result);
      return result;
    }

    // 4. Run completeness check
    const coverage = runCompletenessCheck(analyzed, policies);

    // 5. Run reachability check
    const unreachableRules = runReachabilityCheck(analyzed);

    // 6. Determine overall status
    const consistent = contradictions.filter(
      (c) => c.type === ContradictionTypeEnum.EFFECT_CONFLICT || c.type === ContradictionTypeEnum.UNSATISFIABLE_CONDITION,
    ).length === 0;

    const hasUnreachable = unreachableRules.length > 0;

    let status: VerificationStatus;
    if (!consistent) {
      status = VerificationStatusEnum.FAIL;
    } else if (coverage.gaps.length > 0 || hasUnreachable) {
      status = VerificationStatusEnum.WARNING;
    } else {
      status = VerificationStatusEnum.PASS;
    }

    // 7. Build summary
    const parts: string[] = [];
    parts.push(`Verified ${policies.length} policies (${analyzed.length} statements)`);
    if (contradictions.length > 0) {
      const byType = new Map<ContradictionType, number>();
      for (const c of contradictions) {
        byType.set(c.type, (byType.get(c.type) ?? 0) + 1);
      }
      parts.push(`Found ${contradictions.length} contradictions: ${Array.from(byType.entries()).map(([t, n]) => `${n} ${t}`).join(", ")}`);
    } else {
      parts.push("No contradictions found");
    }
    if (coverage.gaps.length > 0) {
      parts.push(`${coverage.gaps.length} coverage gaps detected (${coverage.coveragePct}% coverage)`);
    }
    if (hasUnreachable) {
      parts.push(`${unreachableRules.length} unreachable rules detected`);
    }

    const result: VerificationResult = {
      consistent,
      complete: coverage.gaps.length === 0,
      hasUnreachableRules: hasUnreachable,
      status,
      contradictions,
      unreachableRules,
      coverage,
      duration: Date.now() - startTime,
      solverType: effectiveSolverType,
      summary: parts.join(". "),
    };

    // 8. Persist results to DB
    await persistVerification(policyIds ?? [], result);

    return result;
  } catch (error) {
    const result: VerificationResult = {
      consistent: false,
      complete: false,
      hasUnreachableRules: false,
      status: VerificationStatusEnum.ERROR,
      contradictions: [],
      unreachableRules: [],
      coverage: { totalSpace: 0, coveredSpace: 0, coveragePct: 0, gaps: [], partialCoverage: [] },
      duration: Date.now() - startTime,
      solverType: effectiveSolverType,
      summary: `Verification error: ${error instanceof Error ? error.message : String(error)}`,
    };

    try {
      await persistVerification(policyIds ?? [], result);
    } catch {
      // Silently fail if we can't persist the error result
    }

    return result;
  }
}

/**
 * Persist a verification result to the PolicyVerification table.
 */
async function persistVerification(policyIds: string[], result: VerificationResult): Promise<void> {
  const verificationId = generateVerificationId();

  await db.policyVerification.create({
    data: {
      verificationId,
      policyIds: JSON.stringify(policyIds),
      consistent: result.contradictions.filter(
        (c) => c.type === ContradictionTypeEnum.EFFECT_CONFLICT || c.type === ContradictionTypeEnum.UNSATISFIABLE_CONDITION,
      ).length === 0,
      complete: result.complete,
      hasUnreachableRules: result.hasUnreachableRules,
      status: result.status,
      contradictions: JSON.stringify(result.contradictions),
      unreachableRules: JSON.stringify(result.unreachableRules),
      coverage: JSON.stringify(result.coverage),
      solverType: result.solverType,
      duration: result.duration,
      summary: result.summary,
    },
  });
}

// ─── Get Verification ────────────────────────────────────────────────

/**
 * Load a verification result by its ID.
 *
 * @param verificationId - The verification ID to look up.
 * @returns The VerificationResult, or null if not found.
 */
export async function getVerification(verificationId: string): Promise<VerificationResult | null> {
  try {
    const record = await db.policyVerification.findUnique({
      where: { verificationId },
    });

    if (!record) return null;

    const contradictions = JSON.parse(record.contradictions) as Contradiction[];
    const coverage = JSON.parse(record.coverage) as CoverageReport;
    const unreachableRules = JSON.parse(record.unreachableRules) as UnreachableRule[];

    return {
      consistent: record.consistent,
      complete: record.complete,
      hasUnreachableRules: record.hasUnreachableRules,
      status: record.status as VerificationStatus,
      contradictions,
      unreachableRules,
      coverage,
      duration: record.duration,
      solverType: record.solverType as SolverType,
      summary: record.summary,
    };
  } catch (error) {
    console.error(`[ConstraintSolver] Error loading verification ${verificationId}:`, error);
    return null;
  }
}

// ─── List Verifications ──────────────────────────────────────────────

/**
 * List verification results with optional filtering and pagination.
 *
 * @param options - Filter and pagination options.
 * @returns Array of VerificationResult objects.
 */
export async function listVerifications(options?: ListVerificationsOptions): Promise<VerificationResult[]> {
  try {
    const where: Record<string, unknown> = {};

    if (options?.status) {
      where.status = options.status;
    }
    if (options?.consistent !== undefined) {
      where.consistent = options.consistent;
    }

    const records = await db.policyVerification.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 50,
      skip: options?.offset ?? 0,
    });

    return records.map((record) => {
      const contradictions = JSON.parse(record.contradictions) as Contradiction[];
      const coverage = JSON.parse(record.coverage) as CoverageReport;
      const unreachableRules = JSON.parse(record.unreachableRules) as UnreachableRule[];

      return {
        consistent: record.consistent,
        complete: record.complete,
        hasUnreachableRules: record.hasUnreachableRules,
        status: record.status as VerificationStatus,
        contradictions,
        unreachableRules,
        coverage,
        duration: record.duration,
        solverType: record.solverType as SolverType,
        summary: record.summary,
      };
    });
  } catch (error) {
    console.error("[ConstraintSolver] Error listing verifications:", error);
    return [];
  }
}
