// ─── Zenic-Agents v3 — Policy Simulator (What-If Analysis) ──────────
// Phase 4: Declarative Versioned Policy Engine — Simulation Module
//
// Design Patterns:
//   - Command: Each SimulationChange is a command that modifies the policy set
//   - Memento: Before/after snapshots for verdict comparison
//   - Strategy: Impact scoring with configurable category weights
//
// Evaluation Flow:
//   1. Load current active policies from DB
//   2. Deep-clone → simulated policy set
//   3. Apply each SimulationChange as a command
//   4. For each test request:
//      a. Evaluate against CURRENT set → "before" result
//      b. Evaluate against SIMULATED set → "after" result
//      c. If different → record as VerdictChange
//   5. Run conflict detection on both sets
//   6. Calculate impact score from verdict changes
//   7. Assess compliance impact
//   8. Persist and return SimulationResult

import { db } from "@/lib/db";
import { PolicyEffectV2 } from "./types";
import type {
  PolicyDocument,
  PolicyStatement,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
} from "./types";
import {
  SimulationChangeType,
  VerdictChangeCategory,
  SimulationRiskLevel,
  ConflictSeverity,
  ConflictType,
  ConflictResolutionStrategy,
} from "./types-v2";
import type {
  SimulationRequest,
  SimulationChange,
  SimulationResult,
  VerdictChange,
  SimulationRisk,
  ComplianceImpact,
  SimulationTrace,
  PolicyConflict,
  ConflictStatementRef,
} from "./types-v2";
import { PolicyEvaluator, getPolicyEvaluator } from "./evaluator";

// ─── Local Types ─────────────────────────────────────────────────────

/** Options for listing simulations */
export interface ListSimulationsOptions {
  /** Filter by requester */
  requestedBy?: string;
  /** Filter by risk level */
  riskLevel?: SimulationRiskLevel;
  /** Maximum results to return */
  limit?: number;
  /** Pagination offset */
  offset?: number;
}

// ─── Deep Clone Helper ───────────────────────────────────────────────

/**
 * Deep clone a value using JSON serialization.
 * Safe for PolicyDocument trees which are plain JSON-compatible objects.
 */
function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

// ─── Pattern Overlap Helper ──────────────────────────────────────────

/**
 * Check if two resource/action patterns could match the same concrete value.
 * Supports wildcard suffixes ("financial/*") and full wildcards ("*").
 */
function patternsOverlap(patternA: string, patternB: string): boolean {
  if (patternA === "*" || patternB === "*") return true;
  if (patternA === patternB) return true;

  // Wildcard suffix: "financial/*" could match anything under "financial/"
  if (patternA.endsWith("/*") && patternB.endsWith("/*")) {
    const prefixA = patternA.slice(0, -2);
    const prefixB = patternB.slice(0, -2);
    return prefixA === prefixB || prefixA.startsWith(`${prefixB}/`) || prefixB.startsWith(`${prefixA}/`);
  }

  // One wildcard, one concrete
  if (patternA.endsWith("/*")) {
    const prefix = patternA.slice(0, -2);
    return patternB === prefix || patternB.startsWith(`${prefix}/`);
  }
  if (patternB.endsWith("/*")) {
    const prefix = patternB.slice(0, -2);
    return patternA === prefix || patternA.startsWith(`${prefix}/`);
  }

  return false;
}

// ─── ID Generation ───────────────────────────────────────────────────

/** Generate a unique simulation ID */
function generateSimulationId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `sim_${ts}_${rand}`;
}

// ─── Load Active Policies ────────────────────────────────────────────

/**
 * Load all active policies from the database and convert to PolicyDocument[].
 * Mirrors PolicyEvaluator.loadActivePolicies logic.
 */
async function loadActivePoliciesFromDb(): Promise<PolicyDocument[]> {
  const policies = await db.declPolicy.findMany({
    where: { isActive: true },
    orderBy: { updatedAt: "desc" },
  });

  return policies.map((p) => ({
    apiVersion: p.apiVersion,
    kind: "PolicyDocument" as const,
    metadata: {
      id: p.policyId,
      name: p.name,
      version: p.version,
      description: p.description,
      compliance: JSON.parse(p.compliance) as import("./types").ComplianceMapping[],
      labels: JSON.parse(p.labels) as Record<string, string>,
      author: p.author ?? undefined,
      createdAt: p.createdAt.toISOString(),
      updatedAt: p.updatedAt.toISOString(),
    },
    statements: JSON.parse(p.statements) as PolicyStatement[],
    tests: JSON.parse(p.tests) as import("./types").PolicyTestCase[],
  }));
}

// ─── Evaluation Against Policy Set ───────────────────────────────────

/**
 * Evaluate a request against an array of policy documents.
 * Collects all matching statements across all documents,
 * sorts by priority (deny wins on tie), and returns the top match.
 *
 * This is the in-memory equivalent of PolicyEvaluator.evaluate()
 * but works with any provided document set (not DB-bound).
 */
function evaluateAgainstPolicySet(
  evaluator: PolicyEvaluator,
  documents: PolicyDocument[],
  request: PolicyEvaluationRequest,
): PolicyEvaluationResult {
  const startTime = Date.now();
  const allMatched: PolicyEvaluationResult["matchedStatements"] = [];

  for (const doc of documents) {
    const result = evaluator.evaluateDocument(doc, request);
    allMatched.push(...result.matchedStatements);
  }

  // Sort by priority (highest first), deny wins on tie
  allMatched.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    const effectOrder: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };
    return (effectOrder[a.effect] ?? 3) - (effectOrder[b.effect] ?? 3);
  });

  let finalEffect: PolicyEffectV2 = PolicyEffectV2.DENY;
  let matchReason = "No matching statement — default effect applied";
  let matchedStatementId: string | undefined;
  let matchedPolicyId = "default";
  let denyByDefault = true;
  let requiredRole: string | undefined;

  if (allMatched.length > 0) {
    const topMatch = allMatched[0]!;
    finalEffect = topMatch.effect;
    matchedStatementId = topMatch.statementId;
    matchedPolicyId = topMatch.policyId;
    denyByDefault = false;
    matchReason = `Matched statement "${topMatch.statementId}" in policy "${topMatch.policyId}" (priority ${topMatch.priority})`;

    // Find the statement for additional data
    for (const doc of documents) {
      if (doc.metadata.id === topMatch.policyId) {
        const stmt = doc.statements.find((s) => s.id === topMatch.statementId);
        if (stmt?.requiredRole) {
          requiredRole = stmt.requiredRole;
        }
        break;
      }
    }
  }

  return {
    effect: finalEffect,
    policyId: matchedPolicyId,
    matchedStatementId,
    reason: matchReason,
    matchedStatements: allMatched,
    duration: Date.now() - startTime,
    denyByDefault,
    requiredRole,
  };
}

// ─── Verdict Classification (Memento comparison) ─────────────────────

/**
 * Classify the category of a verdict change based on before/after effects.
 *
 * Classification rules:
 *   NEW_DENY: allow/conditional → deny (CRITICAL)
 *   NEW_ALLOW: deny → allow (HIGH)
 *   NEW_CONDITIONAL: deny/allow → conditional (MEDIUM)
 *   CONDITIONAL_TO_DENY: conditional → deny (HIGH)
 *   CONDITIONAL_TO_ALLOW: conditional → allow (MEDIUM)
 *   EFFECT_UNCHANGED: same effect but different matched statement (LOW)
 */
function classifyVerdictChange(
  beforeEffect: PolicyEffectV2,
  afterEffect: PolicyEffectV2,
): VerdictChangeCategory {
  if (beforeEffect === afterEffect) {
    return VerdictChangeCategory.EFFECT_UNCHANGED;
  }

  // NEW_DENY: previously allowed/conditional → now denied
  if (
    (beforeEffect === PolicyEffectV2.ALLOW || beforeEffect === PolicyEffectV2.CONDITIONAL) &&
    afterEffect === PolicyEffectV2.DENY
  ) {
    return VerdictChangeCategory.NEW_DENY;
  }

  // NEW_ALLOW: previously denied → now allowed
  if (beforeEffect === PolicyEffectV2.DENY && afterEffect === PolicyEffectV2.ALLOW) {
    return VerdictChangeCategory.NEW_ALLOW;
  }

  // NEW_CONDITIONAL: previously denied/allowed → now conditional
  if (
    (beforeEffect === PolicyEffectV2.DENY || beforeEffect === PolicyEffectV2.ALLOW) &&
    afterEffect === PolicyEffectV2.CONDITIONAL
  ) {
    return VerdictChangeCategory.NEW_CONDITIONAL;
  }

  // CONDITIONAL_TO_DENY: conditional → deny
  if (beforeEffect === PolicyEffectV2.CONDITIONAL && afterEffect === PolicyEffectV2.DENY) {
    return VerdictChangeCategory.CONDITIONAL_TO_DENY;
  }

  // CONDITIONAL_TO_ALLOW: conditional → allow
  if (beforeEffect === PolicyEffectV2.CONDITIONAL && afterEffect === PolicyEffectV2.ALLOW) {
    return VerdictChangeCategory.CONDITIONAL_TO_ALLOW;
  }

  // Fallback (should not reach here for valid PolicyEffectV2 values)
  return VerdictChangeCategory.EFFECT_UNCHANGED;
}

/**
 * Generate a human-readable description for a verdict change.
 */
function describeVerdictChange(
  request: string,
  beforeEffect: PolicyEffectV2,
  afterEffect: PolicyEffectV2,
  category: VerdictChangeCategory,
): string {
  const descriptions: Record<VerdictChangeCategory, string> = {
    [VerdictChangeCategory.NEW_DENY]:
      `[CRITICAL] ${request}: effect changed from ${beforeEffect} → ${afterEffect} (new denial introduced)`,
    [VerdictChangeCategory.NEW_ALLOW]:
      `[HIGH] ${request}: effect changed from ${beforeEffect} → ${afterEffect} (new allowance — security risk)`,
    [VerdictChangeCategory.NEW_CONDITIONAL]:
      `[MEDIUM] ${request}: effect changed from ${beforeEffect} → ${afterEffect} (now conditional)`,
    [VerdictChangeCategory.CONDITIONAL_TO_DENY]:
      `[HIGH] ${request}: effect changed from ${beforeEffect} → ${afterEffect} (conditional became denial)`,
    [VerdictChangeCategory.CONDITIONAL_TO_ALLOW]:
      `[MEDIUM] ${request}: effect changed from ${beforeEffect} → ${afterEffect} (conditional became allowance)`,
    [VerdictChangeCategory.EFFECT_UNCHANGED]:
      `[LOW] ${request}: effect unchanged (${beforeEffect}) but matched different statement`,
  };
  return descriptions[category] ?? `${request}: ${beforeEffect} → ${afterEffect}`;
}

// ─── Change Application (Command Pattern) ────────────────────────────

/**
 * Apply an ADD_POLICY change: add a new policy document to the simulated set.
 */
function applyAddPolicy(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document) {
    console.warn(`[Simulator] ADD_POLICY change missing document, skipping`);
    return policies;
  }
  // Check if policy already exists
  const exists = policies.some((p) => p.metadata.id === change.document!.metadata.id);
  if (exists) {
    console.warn(`[Simulator] ADD_POLICY: policy "${change.document.metadata.id}" already exists, replacing`);
    return policies.map((p) =>
      p.metadata.id === change.document!.metadata.id ? deepClone(change.document!) : p,
    );
  }
  return [...policies, deepClone(change.document)];
}

/**
 * Apply a MODIFY_POLICY change: replace an existing policy document entirely.
 */
function applyModifyPolicy(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document) {
    console.warn(`[Simulator] MODIFY_POLICY change missing document, skipping`);
    return policies;
  }
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] MODIFY_POLICY: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  const updated = deepClone(policies);
  updated[idx] = deepClone(change.document);
  // Preserve the original policy ID if the replacement document doesn't match
  if (updated[idx]!.metadata.id !== change.policyId) {
    updated[idx]!.metadata.id = change.policyId;
  }
  return updated;
}

/**
 * Apply a REMOVE_POLICY change: remove a policy from the simulated set.
 */
function applyRemovePolicy(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] REMOVE_POLICY: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  return policies.filter((p) => p.metadata.id !== change.policyId);
}

/**
 * Apply an ADD_STATEMENT change: add new statements to an existing policy.
 * The change.document.statements array contains the statements to add.
 */
function applyAddStatement(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document?.statements?.length) {
    console.warn(`[Simulator] ADD_STATEMENT change missing statements, skipping`);
    return policies;
  }
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] ADD_STATEMENT: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  const updated = deepClone(policies);
  const newStmts = deepClone(change.document.statements);
  updated[idx]!.statements.push(...newStmts);
  return updated;
}

/**
 * Apply a MODIFY_STATEMENT change: find and replace statements by ID.
 * The change.document.statements array contains replacement statements
 * (matched by their `id` field).
 */
function applyModifyStatement(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document?.statements?.length) {
    console.warn(`[Simulator] MODIFY_STATEMENT change missing statements, skipping`);
    return policies;
  }
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] MODIFY_STATEMENT: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  const updated = deepClone(policies);
  const replacements = deepClone(change.document.statements);
  for (const replacement of replacements) {
    const stmtIdx = updated[idx]!.statements.findIndex((s) => s.id === replacement.id);
    if (stmtIdx !== -1) {
      updated[idx]!.statements[stmtIdx] = replacement;
    } else {
      console.warn(
        `[Simulator] MODIFY_STATEMENT: statement "${replacement.id}" not found in policy "${change.policyId}"`,
      );
    }
  }
  return updated;
}

/**
 * Apply a REMOVE_STATEMENT change: remove statements by ID.
 * The change.document.statements array entries are matched by `id` field;
 * their other fields are ignored.
 */
function applyRemoveStatement(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document?.statements?.length) {
    console.warn(`[Simulator] REMOVE_STATEMENT change missing statements, skipping`);
    return policies;
  }
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] REMOVE_STATEMENT: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  const updated = deepClone(policies);
  const idsToRemove = new Set(change.document.statements.map((s) => s.id));
  updated[idx]!.statements = updated[idx]!.statements.filter((s) => !idsToRemove.has(s.id));
  return updated;
}

/**
 * Apply a CHANGE_PRIORITY change: update a statement's priority.
 * The change.document.statements array contains statements with matching IDs
 * and new `priority` values.
 */
function applyChangePriority(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document?.statements?.length) {
    console.warn(`[Simulator] CHANGE_PRIORITY change missing statements, skipping`);
    return policies;
  }
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] CHANGE_PRIORITY: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  const updated = deepClone(policies);
  for (const priorityChange of change.document.statements) {
    const stmtIdx = updated[idx]!.statements.findIndex((s) => s.id === priorityChange.id);
    if (stmtIdx !== -1) {
      updated[idx]!.statements[stmtIdx]!.priority = priorityChange.priority;
    } else {
      console.warn(
        `[Simulator] CHANGE_PRIORITY: statement "${priorityChange.id}" not found in policy "${change.policyId}"`,
      );
    }
  }
  return updated;
}

/**
 * Apply a CHANGE_CONDITION change: add/modify conditions on a statement.
 * The change.document.statements array contains statements with matching IDs
 * and new `conditions` arrays that replace the existing conditions.
 */
function applyChangeCondition(
  policies: PolicyDocument[],
  change: SimulationChange,
): PolicyDocument[] {
  if (!change.document?.statements?.length) {
    console.warn(`[Simulator] CHANGE_CONDITION change missing statements, skipping`);
    return policies;
  }
  const idx = policies.findIndex((p) => p.metadata.id === change.policyId);
  if (idx === -1) {
    console.warn(`[Simulator] CHANGE_CONDITION: policy "${change.policyId}" not found, skipping`);
    return policies;
  }
  const updated = deepClone(policies);
  for (const condChange of change.document.statements) {
    const stmtIdx = updated[idx]!.statements.findIndex((s) => s.id === condChange.id);
    if (stmtIdx !== -1) {
      updated[idx]!.statements[stmtIdx]!.conditions = deepClone(condChange.conditions ?? []);
    } else {
      console.warn(
        `[Simulator] CHANGE_CONDITION: statement "${condChange.id}" not found in policy "${change.policyId}"`,
      );
    }
  }
  return updated;
}

/**
 * Apply all simulation changes to a policy set (Command pattern dispatcher).
 * Each change is applied sequentially in order.
 * Returns the modified policy set (original is not mutated).
 */
function applySimulationChanges(
  currentPolicies: PolicyDocument[],
  changes: SimulationChange[],
): PolicyDocument[] {
  let policies = deepClone(currentPolicies);

  for (const change of changes) {
    switch (change.type) {
      case SimulationChangeType.ADD_POLICY:
        policies = applyAddPolicy(policies, change);
        break;
      case SimulationChangeType.MODIFY_POLICY:
        policies = applyModifyPolicy(policies, change);
        break;
      case SimulationChangeType.REMOVE_POLICY:
        policies = applyRemovePolicy(policies, change);
        break;
      case SimulationChangeType.ADD_STATEMENT:
        policies = applyAddStatement(policies, change);
        break;
      case SimulationChangeType.MODIFY_STATEMENT:
        policies = applyModifyStatement(policies, change);
        break;
      case SimulationChangeType.REMOVE_STATEMENT:
        policies = applyRemoveStatement(policies, change);
        break;
      case SimulationChangeType.CHANGE_PRIORITY:
        policies = applyChangePriority(policies, change);
        break;
      case SimulationChangeType.CHANGE_CONDITION:
        policies = applyChangeCondition(policies, change);
        break;
      default:
        console.warn(`[Simulator] Unknown change type: ${change.type}, skipping`);
    }
  }

  return policies;
}

// ─── Conflict Detection ──────────────────────────────────────────────

/** Counter for generating unique conflict IDs */
let conflictCounter = 0;

function generateConflictId(): string {
  conflictCounter++;
  return `conflict_${Date.now().toString(36)}_${conflictCounter}`;
}

/**
 * Detect conflicts within a set of policy documents.
 * Checks all statement pairs across all policies for:
 *   - EFFECT_CONTRADICTION: same resource/action, opposite effects (CRITICAL)
 *   - PRIORITY_COLLISION: same priority, different effects on overlapping resources (HIGH)
 *   - SHADOW_RULE: higher-priority deny shadows lower-priority allow (LOW)
 *   - REDUNDANT_RULE: duplicate statements (LOW)
 *   - CONDITION_OVERLAP: overlapping conditions with different effects (MEDIUM)
 */
function detectPolicyConflicts(
  policies: PolicyDocument[],
): PolicyConflict[] {
  const conflicts: PolicyConflict[] = [];

  // Collect all statements with their policy context
  const allStatements: Array<{
    policyId: string;
    version: string;
    statement: PolicyStatement;
  }> = [];

  for (const policy of policies) {
    for (const stmt of policy.statements) {
      allStatements.push({
        policyId: policy.metadata.id,
        version: policy.metadata.version,
        statement: stmt,
      });
    }
  }

  // Check each pair of statements
  for (let i = 0; i < allStatements.length; i++) {
    const a = allStatements[i]!;
    for (let j = i + 1; j < allStatements.length; j++) {
      const b = allStatements[j]!;

      // Skip self-comparisons within the same statement
      if (a.policyId === b.policyId && a.statement.id === b.statement.id) continue;

      const resourceOverlap = patternsOverlap(a.statement.resource, b.statement.resource);
      const actionOverlap = patternsOverlap(a.statement.action, b.statement.action);

      if (!resourceOverlap || !actionOverlap) continue;

      const refA: ConflictStatementRef = {
        policyId: a.policyId,
        version: a.version,
        statementId: a.statement.id,
        effect: a.statement.effect,
        resource: a.statement.resource,
        action: a.statement.action,
      };

      const refB: ConflictStatementRef = {
        policyId: b.policyId,
        version: b.version,
        statementId: b.statement.id,
        effect: b.statement.effect,
        resource: b.statement.resource,
        action: b.statement.action,
      };

      // EFFECT_CONTRADICTION: opposite effects on same resource/action
      if (
        a.statement.effect !== b.statement.effect &&
        (a.statement.effect === PolicyEffectV2.ALLOW || a.statement.effect === PolicyEffectV2.DENY) &&
        (b.statement.effect === PolicyEffectV2.ALLOW || b.statement.effect === PolicyEffectV2.DENY)
      ) {
        conflicts.push({
          id: generateConflictId(),
          type: ConflictType.EFFECT_CONTRADICTION,
          severity: ConflictSeverity.CRITICAL,
          statementA: refA,
          statementB: refB,
          description: `Effect contradiction: "${a.statement.id}" (${a.statement.effect}) vs "${b.statement.id}" (${b.statement.effect}) on resource "${a.statement.resource}" action "${a.statement.action}"`,
          suggestedResolution: ConflictResolutionStrategy.DENY_WINS,
          resolved: false,
        });
        continue;
      }

      // PRIORITY_COLLISION: same priority, different effects
      if (a.statement.priority === b.statement.priority && a.statement.effect !== b.statement.effect) {
        conflicts.push({
          id: generateConflictId(),
          type: ConflictType.PRIORITY_COLLISION,
          severity: ConflictSeverity.HIGH,
          statementA: refA,
          statementB: refB,
          description: `Priority collision: both "${a.statement.id}" and "${b.statement.id}" have priority ${a.statement.priority} but different effects (${a.statement.effect} vs ${b.statement.effect})`,
          suggestedResolution: ConflictResolutionStrategy.PRIORITY_WINS,
          resolved: false,
        });
        continue;
      }

      // CONDITION_OVERLAP: overlapping conditions, different effects
      if (
        a.statement.effect !== b.statement.effect &&
        a.statement.conditions &&
        a.statement.conditions.length > 0 &&
        b.statement.conditions &&
        b.statement.conditions.length > 0
      ) {
        conflicts.push({
          id: generateConflictId(),
          type: ConflictType.CONDITION_OVERLAP,
          severity: ConflictSeverity.MEDIUM,
          statementA: refA,
          statementB: refB,
          description: `Condition overlap: "${a.statement.id}" (${a.statement.effect}) and "${b.statement.id}" (${b.statement.effect}) have overlapping conditions on "${a.statement.resource}:${a.statement.action}"`,
          suggestedResolution: ConflictResolutionStrategy.MERGE_CONDITIONS,
          resolved: false,
        });
        continue;
      }

      // REDUNDANT_RULE: identical statements
      if (
        a.statement.effect === b.statement.effect &&
        a.statement.resource === b.statement.resource &&
        a.statement.action === b.statement.action &&
        a.statement.priority === b.statement.priority
      ) {
        conflicts.push({
          id: generateConflictId(),
          type: ConflictType.REDUNDANT_RULE,
          severity: ConflictSeverity.LOW,
          statementA: refA,
          statementB: refB,
          description: `Redundant rule: "${a.statement.id}" and "${b.statement.id}" are identical`,
          suggestedResolution: ConflictResolutionStrategy.FIRST_MATCH,
          resolved: false,
        });
        continue;
      }

      // SHADOW_RULE: higher-priority rule shadows lower-priority
      if (
        a.statement.effect !== b.statement.effect &&
        a.statement.priority !== b.statement.priority
      ) {
        const higher = a.statement.priority > b.statement.priority ? a : b;
        const lower = a.statement.priority > b.statement.priority ? b : a;
        conflicts.push({
          id: generateConflictId(),
          type: ConflictType.SHADOW_RULE,
          severity: ConflictSeverity.LOW,
          statementA: { ...refA, effect: higher.statement.effect },
          statementB: { ...refB, effect: lower.statement.effect },
          description: `Shadow rule: "${lower.statement.id}" (${lower.statement.effect}, priority ${lower.statement.priority}) is shadowed by "${higher.statement.id}" (${higher.statement.effect}, priority ${higher.statement.priority})`,
          suggestedResolution: ConflictResolutionStrategy.PRIORITY_WINS,
          resolved: false,
        });
      }
    }
  }

  return conflicts;
}

/**
 * Compute a unique key for a conflict based on its statement pair.
 * Used for comparing conflicts between current and simulated sets.
 */
function conflictKey(conflict: PolicyConflict): string {
  const keyA = `${conflict.statementA.policyId}:${conflict.statementA.statementId}`;
  const keyB = `${conflict.statementB.policyId}:${conflict.statementB.statementId}`;
  // Normalize order so A:B == B:A
  return keyA < keyB ? `${keyA}::${keyB}` : `${keyB}::${keyA}`;
}

/**
 * Compare current and simulated conflicts to find new and resolved ones.
 */
function diffConflicts(
  currentConflicts: PolicyConflict[],
  simulatedConflicts: PolicyConflict[],
): { newConflicts: PolicyConflict[]; resolvedConflicts: PolicyConflict[] } {
  const currentKeys = new Set(currentConflicts.map(conflictKey));
  const simulatedKeys = new Set(simulatedConflicts.map(conflictKey));

  const newConflicts = simulatedConflicts.filter((c) => !currentKeys.has(conflictKey(c)));
  const resolvedConflicts = currentConflicts.filter((c) => !simulatedKeys.has(conflictKey(c)));

  return { newConflicts, resolvedConflicts };
}

// ─── Impact Scoring (Strategy Pattern) ───────────────────────────────

/**
 * Impact score weights per verdict change category.
 * Configurable to allow different scoring strategies.
 */
const IMPACT_WEIGHTS: Record<VerdictChangeCategory, number> = {
  [VerdictChangeCategory.NEW_DENY]: 15,
  [VerdictChangeCategory.NEW_ALLOW]: 10,
  [VerdictChangeCategory.NEW_CONDITIONAL]: 5,
  [VerdictChangeCategory.CONDITIONAL_TO_DENY]: 10,
  [VerdictChangeCategory.CONDITIONAL_TO_ALLOW]: 5,
  [VerdictChangeCategory.EFFECT_UNCHANGED]: 0,
};

/** Maximum impact score */
const MAX_IMPACT_SCORE = 100;

/**
 * Calculate impact score based on verdict changes.
 * Each category has a configurable weight; total is capped at 100.
 */
function calculateImpactScore(verdictChanges: VerdictChange[]): number {
  let score = 0;
  for (const change of verdictChanges) {
    score += IMPACT_WEIGHTS[change.category] ?? 0;
  }
  return Math.min(score, MAX_IMPACT_SCORE);
}

/**
 * Determine risk level from impact score.
 *   0-20:  LOW
 *  21-50:  MEDIUM
 *  51-80:  HIGH
 *  81-100: CRITICAL
 */
function determineRiskLevel(score: number): SimulationRiskLevel {
  if (score <= 20) return SimulationRiskLevel.LOW;
  if (score <= 50) return SimulationRiskLevel.MEDIUM;
  if (score <= 80) return SimulationRiskLevel.HIGH;
  return SimulationRiskLevel.CRITICAL;
}

// ─── Compliance Impact Assessment ────────────────────────────────────

/**
 * Assess compliance impact of proposed changes.
 * Collects compliance standards from affected policies and estimates
 * score change based on the severity of verdict changes.
 */
function assessComplianceImpact(
  currentPolicies: PolicyDocument[],
  simulatedPolicies: PolicyDocument[],
  changes: SimulationChange[],
  verdictChanges: VerdictChange[],
): ComplianceImpact {
  // Collect affected policy IDs from changes
  const affectedPolicyIds = new Set(changes.map((c) => c.policyId));

  // Also include policies referenced in verdict changes
  for (const vc of verdictChanges) {
    // Parse the request string (format: "resource:action")
    // Not directly useful for policy ID, but verdict changes indicate affected areas
    void vc; // acknowledge
  }

  // Collect compliance standards from affected policies
  const affectedStandards: string[] = [];
  const standardSections = new Map<string, Set<string>>();

  for (const policy of currentPolicies) {
    if (!affectedPolicyIds.has(policy.metadata.id)) continue;
    const compliance = policy.metadata.compliance ?? [];
    for (const mapping of compliance) {
      if (!affectedStandards.includes(mapping.standard)) {
        affectedStandards.push(mapping.standard);
      }
      const existing = standardSections.get(mapping.standard) ?? new Set<string>();
      for (const section of mapping.sections) {
        existing.add(section);
      }
      standardSections.set(mapping.standard, existing);
    }
  }

  // Also check simulated policies for new compliance mappings
  for (const policy of simulatedPolicies) {
    if (!affectedPolicyIds.has(policy.metadata.id)) continue;
    const compliance = policy.metadata.compliance ?? [];
    for (const mapping of compliance) {
      if (!affectedStandards.includes(mapping.standard)) {
        affectedStandards.push(mapping.standard);
      }
    }
  }

  // Identify new compliance gaps introduced by verdict changes
  const newGaps: string[] = [];
  const newDenials = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_DENY,
  );
  const newAllowances = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_ALLOW,
  );

  // New denials may create operational gaps
  for (const denial of newDenials) {
    newGaps.push(`Potential operational gap: ${denial.request} now denied`);
  }

  // New allowances may create compliance gaps
  for (const allowance of newAllowances) {
    for (const standard of affectedStandards) {
      newGaps.push(`Compliance risk: ${allowance.request} now allowed — may violate ${standard}`);
    }
  }

  // Estimate compliance score change
  // Negative means worse compliance posture
  let scoreChange = 0;
  for (const vc of verdictChanges) {
    switch (vc.category) {
      case VerdictChangeCategory.NEW_DENY:
        scoreChange -= 2; // New denials may break operations
        break;
      case VerdictChangeCategory.NEW_ALLOW:
        scoreChange -= 5; // New allowances may violate compliance
        break;
      case VerdictChangeCategory.CONDITIONAL_TO_DENY:
        scoreChange -= 1;
        break;
      case VerdictChangeCategory.CONDITIONAL_TO_ALLOW:
        scoreChange -= 3;
        break;
      case VerdictChangeCategory.NEW_CONDITIONAL:
        scoreChange -= 1;
        break;
      case VerdictChangeCategory.EFFECT_UNCHANGED:
        scoreChange += 0;
        break;
    }
  }

  return {
    affectedStandards,
    newGaps,
    scoreChange,
  };
}

// ─── Summary Generation ──────────────────────────────────────────────

/**
 * Generate a human-readable summary for a simulation result.
 */
function generateSummary(
  totalRequests: number,
  verdictChanges: VerdictChange[],
  impactScore: number,
  riskLevel: SimulationRiskLevel,
  newConflicts: PolicyConflict[],
  resolvedConflicts: PolicyConflict[],
): string {
  const lines: string[] = [];

  lines.push(`Simulation analyzed ${totalRequests} test request(s).`);

  if (verdictChanges.length === 0) {
    lines.push("No verdict changes detected — proposed changes have no impact on current evaluations.");
  } else {
    const byCategory = new Map<VerdictChangeCategory, number>();
    for (const vc of verdictChanges) {
      byCategory.set(vc.category, (byCategory.get(vc.category) ?? 0) + 1);
    }

    lines.push(`${verdictChanges.length} verdict change(s) detected:`);
    for (const [category, count] of byCategory) {
      lines.push(`  - ${category}: ${count}`);
    }
  }

  lines.push(`Impact score: ${impactScore}/100 (${riskLevel} risk).`);

  if (newConflicts.length > 0) {
    lines.push(`${newConflicts.length} new conflict(s) introduced.`);
  }
  if (resolvedConflicts.length > 0) {
    lines.push(`${resolvedConflicts.length} conflict(s) resolved.`);
  }

  return lines.join(" ");
}

// ─── Public API ──────────────────────────────────────────────────────

/**
 * Run a what-if simulation.
 *
 * Loads current active policies, applies proposed changes to create
 * a simulated set, evaluates each test request against both sets,
 * detects conflicts, calculates impact, and persists the result.
 *
 * @param request - Simulation request with proposed changes and test requests
 * @returns Simulation result with verdict changes, impact score, and risk assessment
 */
export async function runSimulation(
  request: SimulationRequest,
): Promise<SimulationResult> {
  const evaluator = getPolicyEvaluator();

  // Step 1: Load current active policies
  const currentPolicies = await loadActivePoliciesFromDb();

  // Step 2: Apply proposed changes to create simulated set
  const simulatedPolicies = applySimulationChanges(currentPolicies, request.proposedChanges);

  // Step 3: Evaluate each test request against both sets
  const verdictChanges: VerdictChange[] = [];
  const traces: SimulationTrace[] = [];
  let unchangedCount = 0;

  for (const testReq of request.testRequests) {
    // Evaluate against current policies
    const beforeResult = evaluateAgainstPolicySet(evaluator, currentPolicies, testReq);

    // Evaluate against simulated policies
    const afterResult = evaluateAgainstPolicySet(evaluator, simulatedPolicies, testReq);

    // Record trace if requested
    if (request.includeTrace) {
      traces.push({
        request: testReq,
        beforeResult,
        afterResult,
        causingChange: beforeResult.effect !== afterResult.effect
          ? findCausingChange(testReq, request.proposedChanges, evaluator, currentPolicies, simulatedPolicies)
          : undefined,
      });
    }

    // Compare results
    const requestSignature = `${testReq.resource}:${testReq.action}`;

    if (beforeResult.effect !== afterResult.effect) {
      // Verdict changed
      const category = classifyVerdictChange(beforeResult.effect, afterResult.effect);
      verdictChanges.push({
        request: requestSignature,
        beforeEffect: beforeResult.effect,
        afterEffect: afterResult.effect,
        beforeStatementId: beforeResult.matchedStatementId,
        afterStatementId: afterResult.matchedStatementId,
        category,
        description: describeVerdictChange(
          requestSignature,
          beforeResult.effect,
          afterResult.effect,
          category,
        ),
      });
    } else if (beforeResult.matchedStatementId !== afterResult.matchedStatementId) {
      // Same effect but different matched statement
      verdictChanges.push({
        request: requestSignature,
        beforeEffect: beforeResult.effect,
        afterEffect: afterResult.effect,
        beforeStatementId: beforeResult.matchedStatementId,
        afterStatementId: afterResult.matchedStatementId,
        category: VerdictChangeCategory.EFFECT_UNCHANGED,
        description: describeVerdictChange(
          requestSignature,
          beforeResult.effect,
          afterResult.effect,
          VerdictChangeCategory.EFFECT_UNCHANGED,
        ),
      });
    } else {
      unchangedCount++;
    }
  }

  // Step 4: Run conflict detection on both sets
  const currentConflicts = detectPolicyConflicts(currentPolicies);
  const simulatedConflicts = detectPolicyConflicts(simulatedPolicies);
  const { newConflicts, resolvedConflicts } = diffConflicts(currentConflicts, simulatedConflicts);

  // Step 5: Calculate impact score
  const impactScore = calculateImpactScore(verdictChanges);

  // Step 6: Determine risk level
  const riskLevel = determineRiskLevel(impactScore);

  // Step 7: Assess compliance impact
  const complianceImpact = assessComplianceImpact(
    currentPolicies,
    simulatedPolicies,
    request.proposedChanges,
    verdictChanges,
  );

  // Step 8: Count denials and allowances
  const newDenialsCount = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_DENY || vc.category === VerdictChangeCategory.CONDITIONAL_TO_DENY,
  ).length;
  const newAllowancesCount = verdictChanges.filter(
    (vc) => vc.category === VerdictChangeCategory.NEW_ALLOW || vc.category === VerdictChangeCategory.CONDITIONAL_TO_ALLOW,
  ).length;

  // Step 9: Build risk factors
  const riskFactors: string[] = [];
  if (newDenialsCount > 0) {
    riskFactors.push(`${newDenialsCount} new denial(s) introduced — may break existing workflows`);
  }
  if (newAllowancesCount > 0) {
    riskFactors.push(`${newAllowancesCount} new allowance(s) — potential security exposure`);
  }
  if (newConflicts.length > 0) {
    const criticalConflicts = newConflicts.filter((c) => c.severity === ConflictSeverity.CRITICAL).length;
    if (criticalConflicts > 0) {
      riskFactors.push(`${criticalConflicts} critical conflict(s) detected in proposed changes`);
    }
  }
  if (complianceImpact.affectedStandards.length > 0) {
    riskFactors.push(`Compliance standards affected: ${complianceImpact.affectedStandards.join(", ")}`);
  }
  if (complianceImpact.scoreChange < 0) {
    riskFactors.push(`Compliance score estimated to decrease by ${Math.abs(complianceImpact.scoreChange)} points`);
  }

  // Step 10: Generate summary
  const summary = generateSummary(
    request.testRequests.length,
    verdictChanges,
    impactScore,
    riskLevel,
    newConflicts,
    resolvedConflicts,
  );

  // Step 11: Build simulation result
  const simulationId = generateSimulationId();
  const simulatedAt = new Date().toISOString();

  const result: SimulationResult = {
    id: simulationId,
    name: request.name,
    totalRequests: request.testRequests.length,
    verdictChanges,
    unchangedCount,
    newConflicts,
    resolvedConflicts,
    impactScore,
    risk: {
      level: riskLevel,
      factors: riskFactors,
      newDenialsCount,
      newAllowancesCount,
      complianceImpact,
    },
    simulatedAt,
    summary,
    trace: request.includeTrace ? traces : undefined,
  };

  // Step 12: Persist to DB
  try {
    await db.policySimulation.create({
      data: {
        simulationId,
        name: request.name,
        description: request.description,
        proposedChanges: JSON.stringify(request.proposedChanges),
        testRequests: JSON.stringify(request.testRequests),
        verdictChanges: JSON.stringify(verdictChanges),
        newConflicts: JSON.stringify(newConflicts),
        resolvedConflicts: JSON.stringify(resolvedConflicts),
        impactScore,
        riskLevel,
        riskFactors: JSON.stringify(riskFactors),
        complianceImpact: JSON.stringify(complianceImpact),
        totalRequests: request.testRequests.length,
        unchangedCount,
        newDenialsCount,
        newAllowancesCount,
        requestedBy: request.requestedBy,
        includeTrace: request.includeTrace,
        trace: JSON.stringify(request.includeTrace ? traces : []),
        summary,
      },
    });
  } catch (error) {
    console.error("[Simulator] Failed to persist simulation result:", error);
    // Still return the result even if DB persistence fails
  }

  return result;
}

/**
 * Find which proposed change caused a verdict difference.
 * Applies changes one at a time and checks when the verdict changes.
 */
function findCausingChange(
  testReq: PolicyEvaluationRequest,
  changes: SimulationChange[],
  evaluator: PolicyEvaluator,
  currentPolicies: PolicyDocument[],
  simulatedPolicies: PolicyDocument[],
): string | undefined {
  const beforeResult = evaluateAgainstPolicySet(evaluator, currentPolicies, testReq);

  // Apply changes incrementally
  let policies = deepClone(currentPolicies);
  for (const change of changes) {
    policies = applySimulationChanges(policies, [change]);
    const intermediateResult = evaluateAgainstPolicySet(evaluator, policies, testReq);
    if (intermediateResult.effect !== beforeResult.effect) {
      return `${change.type}:${change.policyId}`;
    }
  }

  // Fallback: check final simulated result
  const afterResult = evaluateAgainstPolicySet(evaluator, simulatedPolicies, testReq);
  if (afterResult.effect !== beforeResult.effect && changes.length > 0) {
    return `${changes[changes.length - 1]!.type}:${changes[changes.length - 1]!.policyId}`;
  }

  return undefined;
}

/**
 * Load a simulation result from the database.
 *
 * @param simulationId - The unique simulation ID
 * @returns The simulation result, or null if not found
 */
export async function getSimulation(
  simulationId: string,
): Promise<SimulationResult | null> {
  try {
    const record = await db.policySimulation.findUnique({
      where: { simulationId },
    });

    if (!record) return null;

    return mapDbRecordToResult(record);
  } catch (error) {
    console.error("[Simulator] Failed to load simulation:", error);
    return null;
  }
}

/**
 * List simulations with optional filtering and pagination.
 *
 * @param options - Filter and pagination options
 * @returns Array of simulation results
 */
export async function listSimulations(
  options?: ListSimulationsOptions,
): Promise<SimulationResult[]> {
  try {
    const where: Record<string, unknown> = {};

    if (options?.requestedBy) {
      where.requestedBy = options.requestedBy;
    }
    if (options?.riskLevel) {
      where.riskLevel = options.riskLevel;
    }

    const records = await db.policySimulation.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 50,
      skip: options?.offset ?? 0,
    });

    return records.map(mapDbRecordToResult);
  } catch (error) {
    console.error("[Simulator] Failed to list simulations:", error);
    return [];
  }
}

/**
 * Delete a simulation result from the database.
 *
 * @param simulationId - The unique simulation ID to delete
 * @returns True if deleted, false if not found
 */
export async function deleteSimulation(
  simulationId: string,
): Promise<boolean> {
  try {
    const existing = await db.policySimulation.findUnique({
      where: { simulationId },
    });

    if (!existing) return false;

    await db.policySimulation.delete({
      where: { simulationId },
    });

    return true;
  } catch (error) {
    console.error("[Simulator] Failed to delete simulation:", error);
    return false;
  }
}

// ─── DB Record Mapper ────────────────────────────────────────────────

/**
 * Map a Prisma PolicySimulation record to a SimulationResult type.
 */
function mapDbRecordToResult(
  record: {
    simulationId: string;
    name: string;
    totalRequests: number;
    verdictChanges: string;
    unchangedCount: number;
    newConflicts: string;
    resolvedConflicts: string;
    impactScore: number;
    riskLevel: string;
    riskFactors: string;
    complianceImpact: string;
    newDenialsCount: number;
    newAllowancesCount: number;
    trace: string;
    summary: string;
    createdAt: Date;
    includeTrace: boolean;
  },
): SimulationResult {
  const parsedVerdictChanges = JSON.parse(record.verdictChanges) as VerdictChange[];
  const parsedNewConflicts = JSON.parse(record.newConflicts) as PolicyConflict[];
  const parsedResolvedConflicts = JSON.parse(record.resolvedConflicts) as PolicyConflict[];
  const parsedRiskFactors = JSON.parse(record.riskFactors) as string[];
  const parsedComplianceImpact = JSON.parse(record.complianceImpact) as ComplianceImpact;
  const parsedTrace = record.includeTrace
    ? (JSON.parse(record.trace) as SimulationTrace[])
    : undefined;

  return {
    id: record.simulationId,
    name: record.name,
    totalRequests: record.totalRequests,
    verdictChanges: parsedVerdictChanges,
    unchangedCount: record.unchangedCount,
    newConflicts: parsedNewConflicts,
    resolvedConflicts: parsedResolvedConflicts,
    impactScore: record.impactScore,
    risk: {
      level: record.riskLevel as SimulationRiskLevel,
      factors: parsedRiskFactors,
      newDenialsCount: record.newDenialsCount,
      newAllowancesCount: record.newAllowancesCount,
      complianceImpact: parsedComplianceImpact,
    },
    simulatedAt: record.createdAt.toISOString(),
    summary: record.summary,
    trace: parsedTrace,
  };
}
