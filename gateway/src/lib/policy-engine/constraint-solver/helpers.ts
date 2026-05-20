// ─── Utility Functions ────────────────────────────────────────────────

import type { PolicyCondition } from "../types";
import type { ConditionRange } from "./types";

/** Generate a unique verification ID */
export function generateVerificationId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `vf_${ts}_${rand}`;
}

/** Generate a unique contradiction ID */
export function generateContradictionId(index: number): string {
  return `contra_${index}_${Date.now().toString(36)}`;
}

/** Generate a contradiction ID with field context */
export function generateContradictionIndex(index: number, field: string): string {
  return `contra_${index}_${field.replace(/[^a-zA-Z0-9]/g, "_")}_${Date.now().toString(36)}`;
}

/** Check if two resource:action patterns overlap */
export function patternsOverlap(resourceA: string, actionA: string, resourceB: string, actionB: string): boolean {
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
export function valueMatchesPattern(pattern: string, value: string): boolean {
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
export function extractConditionRange(conditions: PolicyCondition[], field: string): ConditionRange {
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
export function isRangeSatisfiable(range: ConditionRange): { satisfiable: boolean; reason: string } {
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
export function isRangeTautology(range: ConditionRange): { isTautology: boolean; reason: string } {
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
export function areRangesMutuallyExclusive(
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
export function isRangeSubset(rangeA: ConditionRange, rangeB: ConditionRange): boolean {
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
