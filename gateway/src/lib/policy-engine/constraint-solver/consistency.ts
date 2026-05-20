// ─── Policy Loading ───────────────────────────────────────────────────

import { db } from "@/lib/db";
import type { PolicyDocument, PolicyCondition, PolicyEffectV2 } from "../types";
import type { Contradiction } from "../types/constraints";
import { ContradictionType as ContradictionTypeEnum } from "../types/constraints";
import type { AnalyzedStatement, ConditionRange, ConstraintArc, StatementDomain } from "./types";
import { MAX_STATEMENT_PAIRS } from "./types";
import {
  patternsOverlap,
  extractConditionRange,
  isRangeSatisfiable,
  isRangeTautology,
  areRangesMutuallyExclusive,
  generateContradictionId,
  generateContradictionIndex,
} from "./helpers";

/**
 * Load policies from the database.
 * If policyIds is specified, only those policies are loaded.
 * Otherwise, all active policies are loaded.
 */
export async function loadPolicies(policyIds?: string[]): Promise<PolicyDocument[]> {
  const where = policyIds && policyIds.length > 0
    ? { policyId: { in: policyIds }, isActive: true }
    : { isActive: true };

  // BUG #6 FIX: Added take limit to prevent OOM on 500MB Termux host
  const policies = await db.declPolicy.findMany({
    where,
    orderBy: { updatedAt: "desc" },
    take: 200,
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
export function analyzeStatements(policies: PolicyDocument[]): AnalyzedStatement[] {
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
export function runAC3Consistency(
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

/**
 * Check if two analyzed statements have mutually exclusive conditions.
 */
export function checkConditionsMutuallyExclusive(a: AnalyzedStatement, b: AnalyzedStatement): boolean {
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
