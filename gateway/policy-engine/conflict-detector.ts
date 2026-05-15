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
} from "./types-v2";

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

  // Both have conditions — analyze field by field
  const fieldsA = new Map<string, PolicyCondition[]>();
  const fieldsB = new Map<string, PolicyCondition[]>();

  for (const c of conditionsA) {
    const existing = fieldsA.get(c.field) ?? [];
    existing.push(c);
    fieldsA.set(c.field, existing);
  }
  for (const c of conditionsB) {
    const existing = fieldsB.get(c.field) ?? [];
    existing.push(c);
    fieldsB.set(c.field, existing);
  }

  let aSubsetB = true; // A is more restrictive (all of A's constraints are covered by B)
  let bSubsetA = true; // B is more restrictive (all of B's constraints are covered by A)
  let hasOverlap = true;

  // Check each field in A against B
  for (const [field, condsA] of fieldsA) {
    const condsB = fieldsB.get(field);
    if (!condsB) {
      // A constrains a field that B doesn't — A is more restrictive
      bSubsetA = false;
      continue;
    }
    // Both constrain this field — check compatibility
    const relation = compareFieldConditions(condsA, condsB);
    if (relation === "disjoint") {
      hasOverlap = false;
      aSubsetB = false;
      bSubsetA = false;
      break;
    }
    if (relation === "a_stricter") {
      bSubsetA = false; // A is more restrictive on this field, so B is not a subset of A
    }
    if (relation === "b_stricter") {
      aSubsetB = false; // B is more restrictive on this field, so A is not a subset of B
    }
    // "equivalent" or "overlap" don't change subset flags
    if (relation === "overlap") {
      aSubsetB = false;
      bSubsetA = false;
    }
  }

  // Check fields only in B (B constrains fields A doesn't)
  for (const field of fieldsB.keys()) {
    if (!fieldsA.has(field)) {
      aSubsetB = false; // B constrains a field A doesn't — B is more restrictive
    }
  }

  if (!hasOverlap) return "disjoint";
  if (aSubsetB && bSubsetA) return "equal";
  if (aSubsetB) return "a_subset_b";
  if (bSubsetA) return "b_subset_a";
  return "overlap";
}

/**
 * Compare conditions on the same field.
 * Returns the relationship: which is more restrictive, or if they're
 * equivalent, overlapping, or disjoint.
 */
function compareFieldConditions(
  condsA: PolicyCondition[],
  condsB: PolicyCondition[],
): "a_stricter" | "b_stricter" | "equivalent" | "overlap" | "disjoint" {
  // Simplified comparison: check if conditions on the same field
  // constrain to compatible, equivalent, or disjoint value sets
  // For a full implementation, we'd evaluate the operator logic.
  // Here we use a heuristic approach based on operator types and values.

  const valuesA = condsA.map((c) => conditionSignature(c)).sort().join("|");
  const valuesB = condsB.map((c) => conditionSignature(c)).sort().join("|");

  if (valuesA === valuesB) return "equivalent";

  // Check for direct contradictions (e.g., eq:5 vs eq:10 on same field)
  const eqValuesA = condsA.filter((c) => c.operator === "eq").map((c) => String(c.value));
  const eqValuesB = condsB.filter((c) => c.operator === "eq").map((c) => String(c.value));

  if (eqValuesA.length > 0 && eqValuesB.length > 0) {
    const intersection = eqValuesA.filter((v) => eqValuesB.includes(v));
    if (intersection.length === 0) return "disjoint";
  }

  // Heuristic: if one uses "in" with a subset, or "eq" vs "in"
  if (condsA.length === 1 && condsB.length === 1) {
    const a = condsA[0]!;
    const b = condsB[0]!;
    return compareSingleConditions(a, b);
  }

  return "overlap";
}

/**
 * Compare two single conditions on the same field.
 */
function compareSingleConditions(
  a: PolicyCondition,
  b: PolicyCondition,
): "a_stricter" | "b_stricter" | "equivalent" | "overlap" | "disjoint" {
  if (a.operator === b.operator && a.value === b.value) return "equivalent";

  // eq vs in: eq is stricter if the value is in the in-list
  if (a.operator === "eq" && b.operator === "in") {
    if (Array.isArray(b.value) && b.value.includes(a.value)) return "a_stricter";
    return "disjoint";
  }
  if (b.operator === "eq" && a.operator === "in") {
    if (Array.isArray(a.value) && a.value.includes(b.value)) return "b_stricter";
    return "disjoint";
  }

  // eq vs eq with different values: disjoint
  if (a.operator === "eq" && b.operator === "eq") {
    return a.value === b.value ? "equivalent" : "disjoint";
  }

  // gt vs gte: compare thresholds
  if ((a.operator === "gt" || a.operator === "gte") && (b.operator === "gt" || b.operator === "gte")) {
    const valA = typeof a.value === "number" ? a.value : NaN;
    const valB = typeof b.value === "number" ? b.value : NaN;
    if (isNaN(valA) || isNaN(valB)) return "overlap";
    const strictA = a.operator === "gt" ? valA : valA - 0.001;
    const strictB = b.operator === "gt" ? valB : valB - 0.001;
    if (strictA > strictB) return "b_stricter"; // A requires higher value, so B is more permissive
    if (strictB > strictA) return "a_stricter";
    return "equivalent";
  }

  // lt vs lte: compare thresholds
  if ((a.operator === "lt" || a.operator === "lte") && (b.operator === "lt" || b.operator === "lte")) {
    const valA = typeof a.value === "number" ? a.value : NaN;
    const valB = typeof b.value === "number" ? b.value : NaN;
    if (isNaN(valA) || isNaN(valB)) return "overlap";
    const strictA = a.operator === "lt" ? valA : valA + 0.001;
    const strictB = b.operator === "lt" ? valB : valB + 0.001;
    if (strictA < strictB) return "b_stricter";
    if (strictB < strictA) return "a_stricter";
    return "equivalent";
  }

  // gt/gte vs lt/lte: check for disjoint ranges
  if ((a.operator === "gt" || a.operator === "gte") && (b.operator === "lt" || b.operator === "lte")) {
    const low = typeof a.value === "number" ? a.value : NaN;
    const high = typeof b.value === "number" ? b.value : NaN;
    if (!isNaN(low) && !isNaN(high) && low >= high) return "disjoint";
    return "overlap";
  }
  if ((a.operator === "lt" || a.operator === "lte") && (b.operator === "gt" || b.operator === "gte")) {
    const high = typeof a.value === "number" ? a.value : NaN;
    const low = typeof b.value === "number" ? b.value : NaN;
    if (!isNaN(low) && !isNaN(high) && low >= high) return "disjoint";
    return "overlap";
  }

  // Default: assume overlap for complex operator combinations
  return "overlap";
}

/**
 * Generate a comparable signature for a condition.
 */
function conditionSignature(c: PolicyCondition): string {
  return `${c.operator}:${JSON.stringify(c.value)}`;
}

// ─── Statement Containment ────────────────────────────────────────────

/**
 * Check if statement A is entirely contained by statement B.
 * A is contained by B if B's resource/action patterns are a superset
 * and B's conditions are a superset (less restrictive).
 */
function isStatementContainedBy(a: PolicyStatement, b: PolicyStatement): boolean {
  // B's patterns must be at least as broad as A's
  if (!patternContains(b.resource, a.resource)) return false;
  if (!patternContains(b.action, a.action)) return false;

  // B's conditions must be a superset (less restrictive or equivalent)
  const condRelation = analyzeConditionOverlap(a.conditions, b.conditions);
  return condRelation === "a_subset_b" || condRelation === "equal";
}

/**
 * Check if patternOuter contains patternInner.
 * E.g., "financial/*" contains "financial/transfer".
 */
function patternContains(patternOuter: string, patternInner: string): boolean {
  if (patternOuter === "*") return true;
  if (patternOuter === patternInner) return true;

  if (patternOuter.endsWith("/*")) {
    const prefix = patternOuter.slice(0, -2);
    return patternInner === prefix || patternInner.startsWith(`${prefix}/`);
  }

  if (patternOuter.startsWith("*/")) {
    const suffix = patternOuter.slice(1);
    return patternInner.endsWith(suffix) || patternInner === suffix.slice(1);
  }

  return false;
}

// ─── Shadow Rule Detection ────────────────────────────────────────────

/**
 * Check if statement A shadows statement B.
 * A shadows B if:
 * - A has higher priority than B
 * - A's patterns are a superset of B's (A always matches when B matches)
 * - A and B have the same effect (so B never changes the outcome)
 */
function doesStatementShadow(shadow: PolicyStatement, shadowed: PolicyStatement): boolean {
  // Shadow must have strictly higher priority
  if (shadow.priority <= shadowed.priority) return false;

  // Shadow's patterns must contain the shadowed's patterns
  if (!patternContains(shadow.resource, shadowed.resource)) return false;
  if (!patternContains(shadow.action, shadowed.action)) return false;

  // Same effect — the shadowed statement never changes the outcome
  if (shadow.effect !== shadowed.effect) return false;

  // If the shadow has no conditions or is broader, the shadowed is always matched first
  if (!shadow.conditions || shadow.conditions.length === 0) return true;

  // If both have conditions, check if shadow's scope covers shadowed's
  const condRelation = analyzeConditionOverlap(shadowed.conditions, shadow.conditions);
  return condRelation === "a_subset_b" || condRelation === "equal";
}

// ─── Severity Scoring ─────────────────────────────────────────────────

/**
 * Determine severity based on conflict type and effects involved.
 */
function scoreSeverity(
  type: ConflictTypeType,
  effectA: PolicyEffectV2,
  effectB: PolicyEffectV2,
): ConflictSeverityType {
  switch (type) {
    case ConflictType.EFFECT_CONTRADICTION:
      // ALLOW vs DENY is CRITICAL; other contradictions are HIGH
      if (
        (effectA === PolicyEffectV2FromTypes.ALLOW && effectB === PolicyEffectV2FromTypes.DENY) ||
        (effectA === PolicyEffectV2FromTypes.DENY && effectB === PolicyEffectV2FromTypes.ALLOW)
      ) {
        return ConflictSeverity.CRITICAL;
      }
      return ConflictSeverity.HIGH;

    case ConflictType.PRIORITY_COLLISION:
      return ConflictSeverity.HIGH;

    case ConflictType.CONDITION_OVERLAP:
      return ConflictSeverity.MEDIUM;

    case ConflictType.REDUNDANT_RULE:
      return ConflictSeverity.LOW;

    case ConflictType.SHADOW_RULE:
      return ConflictSeverity.INFO;

    case ConflictType.SCOPE_CONFLICT:
      return ConflictSeverity.HIGH;

    default:
      return ConflictSeverity.MEDIUM;
  }
}

/**
 * Local alias to avoid name collision with the imported type
 */
const PolicyEffectV2FromTypes = {
  ALLOW: "allow",
  DENY: "deny",
  CONDITIONAL: "conditional",
} as const;

/**
 * Suggest a resolution strategy based on conflict type.
 */
function suggestResolution(type: ConflictTypeType): ConflictResolutionStrategyType {
  switch (type) {
    case ConflictType.EFFECT_CONTRADICTION:
      return ConflictResolutionStrategy.DENY_WINS;
    case ConflictType.PRIORITY_COLLISION:
      return ConflictResolutionStrategy.PRIORITY_WINS;
    case ConflictType.CONDITION_OVERLAP:
      return ConflictResolutionStrategy.MERGE_CONDITIONS;
    case ConflictType.REDUNDANT_RULE:
      return ConflictResolutionStrategy.FIRST_MATCH;
    case ConflictType.SHADOW_RULE:
      return ConflictResolutionStrategy.FIRST_MATCH;
    case ConflictType.SCOPE_CONFLICT:
      return ConflictResolutionStrategy.MANUAL;
    default:
      return ConflictResolutionStrategy.MANUAL;
  }
}

// ─── Conflict Description Generation ──────────────────────────────────

/**
 * Generate a human-readable description for a conflict.
 */
function generateDescription(
  type: ConflictTypeType,
  refA: ConflictStatementRef,
  refB: ConflictStatementRef,
): string {
  switch (type) {
    case ConflictType.EFFECT_CONTRADICTION:
      return `Effect contradiction: "${refA.statementId}" in policy "${refA.policyId}" (${refA.effect}) ` +
        `conflicts with "${refB.statementId}" in policy "${refB.policyId}" (${refB.effect}) ` +
        `on resource "${refA.resource}" action "${refA.action}"`;

    case ConflictType.PRIORITY_COLLISION:
      return `Priority collision: "${refA.statementId}" in policy "${refA.policyId}" and ` +
        `"${refB.statementId}" in policy "${refB.policyId}" have overlapping scope ` +
        `with same priority level but different effects`;

    case ConflictType.CONDITION_OVERLAP:
      return `Condition overlap: "${refA.statementId}" in policy "${refA.policyId}" and ` +
        `"${refB.statementId}" in policy "${refB.policyId}" have overlapping condition scopes ` +
        `on resource "${refA.resource}" action "${refA.action}"`;

    case ConflictType.REDUNDANT_RULE:
      return `Redundant rule: "${refB.statementId}" in policy "${refB.policyId}" ` +
        `is a subset of "${refA.statementId}" in policy "${refA.policyId}" ` +
        `and does not change the evaluation outcome`;

    case ConflictType.SHADOW_RULE:
      return `Shadow rule: "${refB.statementId}" in policy "${refB.policyId}" ` +
        `is never reached because "${refA.statementId}" in policy "${refA.policyId}" ` +
        `always matches first with the same effect (higher priority)`;

    case ConflictType.SCOPE_CONFLICT:
      return `Scope conflict: "${refA.statementId}" in policy "${refA.policyId}" ` +
        `and "${refB.statementId}" in policy "${refB.policyId}" ` +
        `from different namespaces have overlapping scope`;

    default:
      return `Unknown conflict between "${refA.statementId}" and "${refB.statementId}"`;
  }
}

// ─── Loaded Policy Statement (internal) ───────────────────────────────

interface LoadedStatement {
  policyId: string;
  version: string;
  statement: PolicyStatement;
  namespace?: string;
}

// ─── Conflict Detector Options ────────────────────────────────────────

export interface ConflictDetectionOptions {
  /** Filter by severity */
  severity?: ConflictSeverityType;
  /** Filter by conflict type */
  type?: ConflictTypeType;
  /** Filter by resolved status */
  resolved?: boolean;
  /** Filter by policy ID (checks both policyIdA and policyIdB) */
  policyId?: string;
  /** Maximum number of results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

// ─── Conflict Detector Class ──────────────────────────────────────────

export class ConflictDetector {
  private cache: Map<string, PolicyConflict[]> = new Map();

  /**
   * Detect conflicts across all active policies (or specified ones).
   * Analyzes all statement pairs for conflicts.
   * Persists results to the PolicyConflictRecord DB table.
   */
  async detectConflicts(policies?: string[]): Promise<ConflictReport> {
    const startTime = Date.now();

    // 1. Load policies from DB
    const loadedStatements = await this.loadPolicyStatements(policies);

    if (loadedStatements.length === 0) {
      return {
        generatedAt: new Date().toISOString(),
        totalPolicies: 0,
        totalConflicts: 0,
        bySeverity: this.emptyBySeverity(),
        byType: this.emptyByType(),
        conflicts: [],
        conflictScore: 0,
        summary: "No active policies found — no conflicts to detect.",
      };
    }

    // 2. Clear old conflict records for the analyzed policies
    await this.clearOldConflicts(policies);

    // 3. Analyze all statement pairs
    const conflicts = this.analyzeStatementPairs(loadedStatements);

    // 4. Persist to DB
    await this.persistConflicts(conflicts);

    // 5. Build report
    return this.buildReport(conflicts, loadedStatements, startTime);
  }

  /**
   * Resolve a detected conflict with a chosen strategy.
   */
  async resolveConflict(
    conflictId: string,
    strategy: ConflictResolutionStrategyType,
    resolvedBy: string,
    note: string,
  ): Promise<PolicyConflict | null> {
    const record = await db.policyConflictRecord.findFirst({
      where: { conflictId },
    });

    if (!record) return null;

    const resolution: ConflictResolution = {
      strategy,
      resolvedBy,
      resolvedAt: new Date().toISOString(),
      note,
    };

    await db.policyConflictRecord.update({
      where: { id: record.id },
      data: {
        resolved: true,
        resolutionStrategy: strategy,
        resolvedBy,
        resolutionNote: note,
        resolvedAt: new Date(),
      },
    });

    // Return the updated conflict
    return this.recordToConflict({
      ...record,
      resolved: true,
      resolutionStrategy: strategy,
      resolvedBy,
      resolutionNote: note,
      resolvedAt: new Date(),
    });
  }

  /**
   * Auto-resolve all unresolved conflicts using the given strategy.
   * Returns the number of conflicts resolved.
   */
  async autoResolveConflicts(
    strategy: ConflictResolutionStrategyType = ConflictResolutionStrategy.DENY_WINS,
  ): Promise<{ resolved: number; total: number }> {
    const unresolved = await db.policyConflictRecord.findMany({
      where: { resolved: false },
    });

    if (unresolved.length === 0) {
      return { resolved: 0, total: 0 };
    }

    const resolvedAt = new Date();
    const resolvedBy = "auto-resolver";

    // Batch update all unresolved conflicts
    for (const record of unresolved) {
      // Determine the effective strategy for this conflict
      const effectiveStrategy = this.resolveStrategyForConflict(record, strategy);

      await db.policyConflictRecord.update({
        where: { id: record.id },
        data: {
          resolved: true,
          resolutionStrategy: effectiveStrategy,
          resolvedBy,
          resolutionNote: `Auto-resolved using ${effectiveStrategy} strategy`,
          resolvedAt,
        },
      });
    }

    return { resolved: unresolved.length, total: unresolved.length };
  }

  /**
   * Generate a summary ConflictReport.
   */
  async getConflictReport(): Promise<ConflictReport> {
    const allConflicts = await db.policyConflictRecord.findMany({
      orderBy: { createdAt: "desc" },
    });

    const conflicts = allConflicts.map((r) => this.recordToConflict(r));
    const totalPolicies = await db.declPolicy.count({ where: { isActive: true } });

    const bySeverity = this.emptyBySeverity();
    const byType = this.emptyByType();

    for (const c of conflicts) {
      bySeverity[c.severity] = (bySeverity[c.severity] ?? 0) + 1;
      byType[c.type] = (byType[c.type] ?? 0) + 1;
    }

    const conflictScore = this.computeConflictScore(conflicts);
    const summary = this.formatSummary(conflicts.length, conflictScore, totalPolicies);

    return {
      generatedAt: new Date().toISOString(),
      totalPolicies,
      totalConflicts: conflicts.length,
      bySeverity,
      byType,
      conflicts,
      conflictScore,
      summary,
    };
  }

  /**
   * Query conflicts with filtering options.
   */
  async getConflicts(options?: ConflictDetectionOptions): Promise<PolicyConflict[]> {
    const where: Record<string, unknown> = {};

    if (options?.severity) {
      where.severity = options.severity;
    }
    if (options?.type) {
      where.type = options.type;
    }
    if (options?.resolved !== undefined) {
      where.resolved = options.resolved;
    }
    if (options?.policyId) {
      where.OR = [
        { policyIdA: options.policyId },
        { policyIdB: options.policyId },
      ];
    }

    const records = await db.policyConflictRecord.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 100,
      skip: options?.offset ?? 0,
    });

    return records.map((r) => this.recordToConflict(r));
  }

  // ─── Private: Policy Loading ──────────────────────────────────────

  /**
   * Load policy statements from DB.
   */
  private async loadPolicyStatements(policyIds?: string[]): Promise<LoadedStatement[]> {
    const where: Record<string, unknown> = { isActive: true };
    if (policyIds && policyIds.length > 0) {
      where.policyId = { in: policyIds };
    }

    const policies = await db.declPolicy.findMany({
      where,
      orderBy: { updatedAt: "desc" },
    });

    const statements: LoadedStatement[] = [];

    for (const policy of policies) {
      let parsedStatements: PolicyStatement[];
      try {
        parsedStatements = JSON.parse(policy.statements);
      } catch {
        continue; // Skip policies with invalid JSON
      }

      // Try to resolve namespace from labels
      let namespace: string | undefined;
      try {
        const labels = JSON.parse(policy.labels);
        if (labels && typeof labels === "object") {
          namespace = (labels as Record<string, string>).namespace;
        }
      } catch {
        // No namespace
      }

      for (const stmt of parsedStatements) {
        statements.push({
          policyId: policy.policyId,
          version: policy.version,
          statement: stmt,
          namespace,
        });
      }
    }

    return statements;
  }

  // ─── Private: Statement Pair Analysis ─────────────────────────────

  /**
   * Analyze all statement pairs for conflicts.
   * Uses a Visitor-like traversal pattern.
   */
  private analyzeStatementPairs(statements: LoadedStatement[]): PolicyConflict[] {
    const conflicts: PolicyConflict[] = [];
    const seen = new Set<string>();

    for (let i = 0; i < statements.length; i++) {
      for (let j = i + 1; j < statements.length; j++) {
        const a = statements[i]!;
        const b = statements[j]!;

        // Skip self-comparison within same statement
        if (a.policyId === b.policyId && a.statement.id === b.statement.id) continue;

        const pairConflicts = this.analyzePair(a, b);
        for (const conflict of pairConflicts) {
          // Deduplicate by generating a unique key
          const key = this.conflictKey(conflict);
          if (!seen.has(key)) {
            seen.add(key);
            conflicts.push(conflict);
          }
        }
      }
    }

    return conflicts;
  }

  /**
   * Analyze a single pair of loaded statements for all possible conflicts.
   */
  private analyzePair(a: LoadedStatement, b: LoadedStatement): PolicyConflict[] {
    const conflicts: PolicyConflict[] = [];
    const stmtA = a.statement;
    const stmtB = b.statement;

    // Check if resource/action patterns overlap
    const patternsOverlap = statementPatternsOverlap(stmtA, stmtB);
    if (!patternsOverlap) return conflicts;

    // Build statement references
    const refA: ConflictStatementRef = {
      policyId: a.policyId,
      version: a.version,
      statementId: stmtA.id,
      effect: stmtA.effect,
      resource: stmtA.resource,
      action: stmtA.action,
    };
    const refB: ConflictStatementRef = {
      policyId: b.policyId,
      version: b.version,
      statementId: stmtB.id,
      effect: stmtB.effect,
      resource: stmtB.resource,
      action: stmtB.action,
    };

    // 1. EFFECT_CONTRADICTION: same resource/action overlap, different effects
    if (stmtA.effect !== stmtB.effect) {
      conflicts.push(this.makeConflict(
        ConflictType.EFFECT_CONTRADICTION,
        refA, refB,
      ));

      // Also check PRIORITY_COLLISION if same priority
      if (stmtA.priority === stmtB.priority) {
        conflicts.push(this.makeConflict(
          ConflictType.PRIORITY_COLLISION,
          refA, refB,
        ));
      }
    } else {
      // Same effect — check for other conflict types

      // 2. PRIORITY_COLLISION: same priority, same effect but overlapping scope
      if (stmtA.priority === stmtB.priority && stmtA.effect === stmtB.effect) {
        // Same effect and priority isn't necessarily a conflict,
        // but overlapping conditions make it ambiguous
        const condRelation = analyzeConditionOverlap(stmtA.conditions, stmtB.conditions);
        if (condRelation !== "disjoint") {
          conflicts.push(this.makeConflict(
            ConflictType.PRIORITY_COLLISION,
            refA, refB,
          ));
        }
      }
    }

    // 3. CONDITION_OVERLAP: overlapping condition scopes
    const condRelation = analyzeConditionOverlap(stmtA.conditions, stmtB.conditions);
    if (condRelation === "overlap" || condRelation === "a_subset_b" || condRelation === "b_subset_a") {
      // Only report condition overlap if not already captured by other types
      const isAlreadyCovered = conflicts.some(
        (c) => c.type === ConflictType.EFFECT_CONTRADICTION || c.type === ConflictType.PRIORITY_COLLISION,
      );
      if (!isAlreadyCovered) {
        conflicts.push(this.makeConflict(
          ConflictType.CONDITION_OVERLAP,
          refA, refB,
        ));
      }
    }

    // 4. REDUNDANT_RULE: one statement is a subset of another
    if (isStatementContainedBy(stmtB, stmtA)) {
      conflicts.push(this.makeConflict(
        ConflictType.REDUNDANT_RULE,
        refA, refB,
      ));
    } else if (isStatementContainedBy(stmtA, stmtB)) {
      conflicts.push(this.makeConflict(
        ConflictType.REDUNDANT_RULE,
        refB, refA,
      ));
    }

    // 5. SHADOW_RULE: higher-priority statement shadows lower-priority
    if (doesStatementShadow(stmtA, stmtB)) {
      conflicts.push(this.makeConflict(
        ConflictType.SHADOW_RULE,
        refA, refB,
      ));
    } else if (doesStatementShadow(stmtB, stmtA)) {
      conflicts.push(this.makeConflict(
        ConflictType.SHADOW_RULE,
        refB, refA,
      ));
    }

    // 6. SCOPE_CONFLICT: policies from different namespaces with overlapping scope
    if (a.namespace && b.namespace && a.namespace !== b.namespace) {
      conflicts.push(this.makeConflict(
        ConflictType.SCOPE_CONFLICT,
        refA, refB,
      ));
    }

    return conflicts;
  }

  /**
   * Create a PolicyConflict object.
   */
  private makeConflict(
    type: ConflictTypeType,
    refA: ConflictStatementRef,
    refB: ConflictStatementRef,
  ): PolicyConflict {
    const severity = scoreSeverity(type, refA.effect, refB.effect);
    const suggestedResolution = suggestResolution(type);

    return {
      id: this.generateConflictId(type, refA, refB),
      type,
      severity,
      statementA: refA,
      statementB: refB,
      description: generateDescription(type, refA, refB),
      suggestedResolution,
      resolved: false,
    };
  }

  /**
   * Generate a unique conflict ID.
   */
  private generateConflictId(
    type: ConflictTypeType,
    refA: ConflictStatementRef,
    refB: ConflictStatementRef,
  ): string {
    // Deterministic ID based on conflict content
    const raw = `${type}:${refA.policyId}:${refA.statementId}:${refB.policyId}:${refB.statementId}`;
    const hash = computeContentHash({
      apiVersion: "policy.zenic.dev/v1",
      kind: "PolicyDocument",
      metadata: { id: raw, name: "conflict", version: "1.0.0", description: "" },
      statements: [],
    });
    return `conflict_${hash.slice(0, 16)}`;
  }

  /**
   * Generate a deduplication key for a conflict.
   */
  private conflictKey(conflict: PolicyConflict): string {
    // Normalize ordering so A↔B and B↔A produce the same key
    const ids = [conflict.statementA.policyId + ":" + conflict.statementA.statementId,
      conflict.statementB.policyId + ":" + conflict.statementB.statementId].sort();
    return `${conflict.type}:${ids[0]}:${ids[1]}`;
  }

  // ─── Private: DB Operations ───────────────────────────────────────

  /**
   * Clear old conflict records for the analyzed policies.
   */
  private async clearOldConflicts(policyIds?: string[]): Promise<void> {
    if (policyIds && policyIds.length > 0) {
      await db.policyConflictRecord.deleteMany({
        where: {
          OR: [
            { policyIdA: { in: policyIds } },
            { policyIdB: { in: policyIds } },
          ],
        },
      });
    } else {
      // Clear all conflict records on full scan
      await db.policyConflictRecord.deleteMany({});
    }
  }

  /**
   * Persist detected conflicts to the PolicyConflictRecord table.
   */
  private async persistConflicts(conflicts: PolicyConflict[]): Promise<void> {
    if (conflicts.length === 0) return;

    // Batch insert using createMany for efficiency
    const records = conflicts.map((c) => ({
      conflictId: c.id,
      type: c.type,
      severity: c.severity,
      policyIdA: c.statementA.policyId,
      versionA: c.statementA.version,
      statementIdA: c.statementA.statementId,
      effectA: c.statementA.effect,
      resourceA: c.statementA.resource,
      actionA: c.statementA.action,
      policyIdB: c.statementB.policyId,
      versionB: c.statementB.version,
      statementIdB: c.statementB.statementId,
      effectB: c.statementB.effect,
      resourceB: c.statementB.resource,
      actionB: c.statementB.action,
      description: c.description,
      suggestedResolution: c.suggestedResolution,
      resolved: c.resolved,
    }));

    // Insert in chunks to avoid SQLite limits
    const CHUNK_SIZE = 50;
    for (let i = 0; i < records.length; i += CHUNK_SIZE) {
      const chunk = records.slice(i, i + CHUNK_SIZE);
      await db.policyConflictRecord.createMany({ data: chunk, skipDuplicates: true });
    }
  }

  /**
   * Convert a DB record to a PolicyConflict object.
   */
  private recordToConflict(
    record: Awaited<ReturnType<typeof db.policyConflictRecord.findFirst>> & {
      resolvedAt?: Date | null;
    },
  ): PolicyConflict {
    const refA: ConflictStatementRef = {
      policyId: record.policyIdA,
      version: record.versionA ?? "unknown",
      statementId: record.statementIdA,
      effect: record.effectA as PolicyEffectV2,
      resource: record.resourceA,
      action: record.actionA,
    };

    const refB: ConflictStatementRef = {
      policyId: record.policyIdB,
      version: record.versionB ?? "unknown",
      statementId: record.statementIdB,
      effect: record.effectB as PolicyEffectV2,
      resource: record.resourceB,
      action: record.actionB,
    };

    let resolution: ConflictResolution | undefined;
    if (record.resolved && record.resolutionStrategy) {
      resolution = {
        strategy: record.resolutionStrategy as ConflictResolutionStrategyType,
        resolvedBy: record.resolvedBy ?? "unknown",
        resolvedAt: record.resolvedAt ? new Date(record.resolvedAt).toISOString() : new Date().toISOString(),
        note: record.resolutionNote ?? "",
      };
    }

    return {
      id: record.conflictId,
      type: record.type as ConflictTypeType,
      severity: record.severity as ConflictSeverityType,
      statementA: refA,
      statementB: refB,
      description: record.description,
      suggestedResolution: record.suggestedResolution as ConflictResolutionStrategyType,
      resolved: record.resolved,
      resolution,
    };
  }

  // ─── Private: Resolution Strategy Selection ───────────────────────

  /**
   * Determine the effective resolution strategy for a conflict
   * during auto-resolution.
   */
  private resolveStrategyForConflict(
    record: { type: string; suggestedResolution: string },
    defaultStrategy: ConflictResolutionStrategyType,
  ): ConflictResolutionStrategyType {
    // For effect contradictions, always use deny_wins unless overridden
    if (record.type === ConflictType.EFFECT_CONTRADICTION && defaultStrategy === ConflictResolutionStrategy.DENY_WINS) {
      return ConflictResolutionStrategy.DENY_WINS;
    }

    // For scope conflicts, always require manual resolution
    if (record.type === ConflictType.SCOPE_CONFLICT) {
      return ConflictResolutionStrategy.MANUAL;
    }

    return defaultStrategy;
  }

  // ─── Private: Report Building ─────────────────────────────────────

  /**
   * Build a ConflictReport from detected conflicts.
   */
  private buildReport(
    conflicts: PolicyConflict[],
    statements: LoadedStatement[],
    startTime: number,
  ): ConflictReport {
    const uniquePolicies = new Set(statements.map((s) => s.policyId));
    const bySeverity = this.emptyBySeverity();
    const byType = this.emptyByType();

    for (const c of conflicts) {
      bySeverity[c.severity] = (bySeverity[c.severity] ?? 0) + 1;
      byType[c.type] = (byType[c.type] ?? 0) + 1;
    }

    const conflictScore = this.computeConflictScore(conflicts);
    const summary = this.formatSummary(conflicts.length, conflictScore, uniquePolicies.size);

    return {
      generatedAt: new Date().toISOString(),
      totalPolicies: uniquePolicies.size,
      totalConflicts: conflicts.length,
      bySeverity,
      byType,
      conflicts,
      conflictScore,
      summary,
    };
  }

  /**
   * Compute the conflict score (0-100, lower is better).
   * Weighted by severity: CRITICAL=25, HIGH=15, MEDIUM=8, LOW=3, INFO=1
   * Capped at 100.
   */
  private computeConflictScore(conflicts: PolicyConflict[]): number {
    const WEIGHTS: Record<ConflictSeverityType, number> = {
      [ConflictSeverity.CRITICAL]: 25,
      [ConflictSeverity.HIGH]: 15,
      [ConflictSeverity.MEDIUM]: 8,
      [ConflictSeverity.LOW]: 3,
      [ConflictSeverity.INFO]: 1,
    };

    let score = 0;
    for (const c of conflicts) {
      // Unresolved conflicts count fully; resolved ones count 20%
      const weight = c.resolved ? WEIGHTS[c.severity] * 0.2 : WEIGHTS[c.severity];
      score += weight;
    }

    return Math.min(100, Math.round(score));
  }

  /**
   * Format a summary string for the conflict report.
   */
  private formatSummary(totalConflicts: number, conflictScore: number, totalPolicies: number): string {
    if (totalConflicts === 0) {
      return `No conflicts detected across ${totalPolicies} active policies. Conflict score: 0 (excellent).`;
    }

    let grade: string;
    if (conflictScore <= 10) grade = "good";
    else if (conflictScore <= 30) grade = "fair";
    else if (conflictScore <= 60) grade = "poor";
    else grade = "critical";

    return `Detected ${totalConflicts} conflict${totalConflicts !== 1 ? "s" : ""} across ` +
      `${totalPolicies} active policies. Conflict score: ${conflictScore}/100 (${grade}). ` +
      `Review and resolve critical conflicts first.`;
  }

  /**
   * Create an empty by-severity map.
   */
  private emptyBySeverity(): Record<ConflictSeverityType, number> {
    return {
      [ConflictSeverity.CRITICAL]: 0,
      [ConflictSeverity.HIGH]: 0,
      [ConflictSeverity.MEDIUM]: 0,
      [ConflictSeverity.LOW]: 0,
      [ConflictSeverity.INFO]: 0,
    };
  }

  /**
   * Create an empty by-type map.
   */
  private emptyByType(): Record<ConflictTypeType, number> {
    return {
      [ConflictType.EFFECT_CONTRADICTION]: 0,
      [ConflictType.PRIORITY_COLLISION]: 0,
      [ConflictType.CONDITION_OVERLAP]: 0,
      [ConflictType.REDUNDANT_RULE]: 0,
      [ConflictType.SHADOW_RULE]: 0,
      [ConflictType.SCOPE_CONFLICT]: 0,
    };
  }

  /**
   * Clear the internal cache.
   */
  clearCache(): void {
    this.cache.clear();
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let detectorInstance: ConflictDetector | null = null;

/**
 * Get the singleton ConflictDetector instance.
 */
export function getConflictDetector(): ConflictDetector {
  if (!detectorInstance) {
    detectorInstance = new ConflictDetector();
  }
  return detectorInstance;
}

/**
 * Reset the singleton ConflictDetector instance.
 */
export function resetConflictDetector(): void {
  if (detectorInstance) {
    detectorInstance.clearCache();
  }
  detectorInstance = null;
}
