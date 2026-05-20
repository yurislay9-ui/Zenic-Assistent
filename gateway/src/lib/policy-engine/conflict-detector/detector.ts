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
