// ─── Reachability Check ──────────────────────────────────────────────
// Checks for unreachable (shadowed) rules in the constraint solver.

import type { AnalyzedStatement, ConditionRange } from "./types";
import type { UnreachableRule } from "../types/constraints";
import { patternsOverlap } from "./helpers";
import { isRangeSubset } from "./ranges";

/**
 * Check for unreachable (shadowed) rules.
 * A rule is unreachable if a higher-priority rule always matches first
 * for the same resource:action with the same or broader conditions.
 */
export function runReachabilityCheck(analyzed: AnalyzedStatement[]): UnreachableRule[] {
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
export function rangesEquivalent(a: ConditionRange, b: ConditionRange): boolean {
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
