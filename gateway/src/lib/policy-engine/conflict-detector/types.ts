// ─── Zenic-Agents v3 — Policy Conflict Detector & Resolver ────────────
// Phase 4: Declarative Versioned Policy Engine — Conflict Detection
//
// Detects conflicts across policy statements: effect contradictions,
// priority collisions, condition overlaps, redundant rules, shadow rules,
// and scope conflicts. Supports multiple resolution strategies.
//
// Design Patterns:
//   - Strategy: Pluggable conflict resolution strategies
//   - Visitor: Traversal of policy statements for analysis
//   - Repository: DB operations via Prisma
//   - Singleton: Single ConflictDetector instance

import { db } from "@/lib/db";
import { computeContentHash } from "./yaml-loader";
import type {
  PolicyDocument,
  PolicyStatement,
  PolicyCondition,
  PolicyEffectV2,
} from "./types";
import {
  ConflictSeverity,
  ConflictType,
  ConflictResolutionStrategy,
  type PolicyConflict,
  type ConflictSeverity as ConflictSeverityType,
  type ConflictType as ConflictTypeType,
  type ConflictResolutionStrategy as ConflictResolutionStrategyType,
  type ConflictStatementRef,
  type ConflictResolution,
  type ConflictReport,
} from "./types";

// ─── Pattern Matching (shared with evaluator) ─────────────────────────

/**
 * Check if a concrete value matches a pattern.
 * Supports wildcard: "*" matches everything, "financial/*" matches "financial/transfer".
 */
function matchesPattern(pattern: string, value: string): boolean {
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

  return false;
}

/**
 * Check if two resource/action patterns overlap.
 * Two patterns overlap if there exists at least one concrete value
 * that both could match. This is a conservative over-approximation.
 */
function patternsOverlap(patternA: string, patternB: string): boolean {
  // Exact same pattern
  if (patternA === patternB) return true;

  // Either is global wildcard
  if (patternA === "*" || patternB === "*") return true;

  // Both end with /* — check if prefixes overlap
  if (patternA.endsWith("/*") && patternB.endsWith("/*")) {
    const prefixA = patternA.slice(0, -2);
    const prefixB = patternB.slice(0, -2);
    // Prefixes overlap if one is a prefix of the other
    return prefixA.startsWith(prefixB) || prefixB.startsWith(prefixA) || prefixA === prefixB;
  }

  // One ends with /*, other is exact or different wildcard
  if (patternA.endsWith("/*")) {
    const prefix = patternA.slice(0, -2);
    return patternB === prefix || patternB.startsWith(`${prefix}/`);
  }
  if (patternB.endsWith("/*")) {
    const prefix = patternB.slice(0, -2);
    return patternA === prefix || patternA.startsWith(`${prefix}/`);
  }

  // Both start with */ — check if suffixes overlap
  if (patternA.startsWith("*/") && patternB.startsWith("*/")) {
    const suffixA = patternA.slice(1);
    const suffixB = patternB.slice(1);
    return suffixA.endsWith(suffixB) || suffixB.endsWith(suffixA) || suffixA === suffixB;
  }

  // One starts with */ — other is exact
  if (patternA.startsWith("*/")) {
    const suffix = patternA.slice(1);
    return patternB.endsWith(suffix);
  }
  if (patternB.startsWith("*/")) {
    const suffix = patternB.slice(1);
    return patternA.endsWith(suffix);
  }

  // Both are exact strings — already checked equality above
  return false;
}

/**
 * Check if two statements' resource/action patterns overlap.
 */
function statementPatternsOverlap(a: PolicyStatement, b: PolicyStatement): boolean {
  return patternsOverlap(a.resource, b.resource) && patternsOverlap(a.action, b.action);
}

// ─── Condition Overlap Detection ──────────────────────────────────────

/**
 * Check if one condition set is a subset of another.
 * A condition set A is a subset of B if every request matching A
 * would also match B (B is more general or equal).
 *
 * Returns:
 *   "a_subset_b" — A is a subset of B (B is more general)
 *   "b_subset_a" — B is a subset of A (A is more general)
 *   "overlap"    — They overlap but neither is a subset
 *   "disjoint"   — No overlap between the condition scopes
 *   "equal"      — Conditions are equivalent
 */
function analyzeConditionOverlap(
  conditionsA: PolicyCondition[] | undefined,
  conditionsB: PolicyCondition[] | undefined,
): "a_subset_b" | "b_subset_a" | "overlap" | "disjoint" | "equal" {
  // If neither has conditions, they overlap on the same scope
  if ((!conditionsA || conditionsA.length === 0) && (!conditionsB || conditionsB.length === 0)) {
    return "equal";
  }

  // If A has no conditions but B does, A is more general (B subset of A)
  if (!conditionsA || conditionsA.length === 0) {
    return "b_subset_a";
  }

  // If B has no conditions but A does, B is more general (A subset of B)
  if (!conditionsB || conditionsB.length === 0) {
    return "a_subset_b";
  }

