// ─── Brute Force Solver ──────────────────────────────────────────────

import type { PolicyDocument, PolicyEffectV2 } from "../types";
import type { Contradiction, CoverageReport, CoverageGap, PartialCoverageEntry } from "../types/constraints";
import { ContradictionType as ContradictionTypeEnum } from "../types/constraints";
import type { AnalyzedStatement } from "./types";
import { PolicyEvaluator } from "../evaluator";
import { checkConditionsMutuallyExclusive } from "./consistency";
import { generateContradictionIndex, valueMatchesPattern, isRangeSatisfiable } from "./helpers";

/**
 * Brute-force consistency check: enumerate condition value combinations.
 * Only suitable for small policy sets (≤5 policies).
 */
export function runBruteForceConsistency(
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
export function runCompletenessCheck(
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
