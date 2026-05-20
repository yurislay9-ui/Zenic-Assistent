// ─── Zenic-Agents v3 — Policy Composition Engine ────────────────────────
// Phase 4: Declarative Versioned Policy Engine — Composition Module
//
// Composes multiple PolicyDocuments into a single merged document
// using configurable merge strategies (Strategy pattern).
//
// Design Patterns:
//   - Composite: PolicySet composes multiple PolicyDocuments
//   - Strategy: Pluggable merge strategies (union, intersection, override, extend, priority_merge)
//   - Builder: MergedDocumentBuilder for constructing composed documents
//   - Singleton: CompositionEngine instance management

import { createHash } from "crypto";
import { db } from "@/lib/db";
import { computeContentHash } from "./yaml-loader";
import type {
  PolicyDocument,
  PolicyStatement,
  PolicyEffectV2,
} from "./types";
import {
  POLICY_SET_API_VERSION,
  POLICY_SET_KIND,
  type PolicySet,
  type PolicySetEntry,
  type MergeStrategy,
  type ComposedPolicyResult,
  type CompositionStats,
  type PolicyConflict,
  type ConflictType,
  type ConflictSeverity,
  type ConflictResolutionStrategy,
  type ConflictStatementRef,
} from "./types";

// ─── Constants ────────────────────────────────────────────────────────

const VALID_MERGE_STRATEGIES: ReadonlySet<string> = new Set([
  "union",
  "intersection",
  "override",
  "extend",
  "priority_merge",
]);

const EFFECT_ORDER: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };

// ─── Statement Fingerprinting ─────────────────────────────────────────

/**
 * Create a deterministic fingerprint for a statement for deduplication.
 * Two statements are considered "exact duplicates" if they share the same
 * id, effect, resource, action, and conditions.
 */
function statementFingerprint(stmt: PolicyStatement): string {
  const core = {
    id: stmt.id,
    effect: stmt.effect,
    resource: stmt.resource,
    action: stmt.action,
    conditions: stmt.conditions ?? [],
  };
  return createHash("sha256")
    .update(JSON.stringify(core))
    .digest("hex");
}

/**
 * Create a resource+action key for intersection matching.
 */
function resourceActionKey(stmt: PolicyStatement): string {
  return `${stmt.resource}::${stmt.action}`;
}

// ─── Merge Strategy: UNION ────────────────────────────────────────────

/**
 * UNION merge: Collect all statements from all policies,
 * remove exact duplicates (same id, effect, resource, action, conditions),
 * sort by priority (highest first).
 */
function mergeUnion(
  policyStatements: PolicyStatement[][],
): { statements: PolicyStatement[]; stats: Pick<CompositionStats, "unionCount" | "duplicatesRemoved"> } {
  const seen = new Map<string, PolicyStatement>();
  let duplicatesRemoved = 0;

  for (const stmts of policyStatements) {
    for (const stmt of stmts) {
      const fp = statementFingerprint(stmt);
      if (seen.has(fp)) {
        duplicatesRemoved++;
      } else {
        seen.set(fp, stmt);
      }
    }
  }

  const statements = [...seen.values()].sort((a, b) => b.priority - a.priority);

  return {
    statements,
    stats: {
      unionCount: statements.length,
      duplicatesRemoved,
    },
  };
}

// ─── Merge Strategy: INTERSECTION ─────────────────────────────────────

/**
 * INTERSECTION merge: Only include statements where the same resource+action
 * pair exists in ALL policies. If different effects for same pair, deny wins.
 */
function mergeIntersection(
  policyStatements: PolicyStatement[][],
): { statements: PolicyStatement[]; stats: Pick<CompositionStats, "intersectionCount" | "duplicatesRemoved">; conflicts: PolicyConflict[] } {
  if (policyStatements.length === 0) {
    return { statements: [], stats: { intersectionCount: 0, duplicatesRemoved: 0 }, conflicts: [] };
  }

  if (policyStatements.length === 1) {
    return {
      statements: policyStatements[0]!.sort((a, b) => b.priority - a.priority),
      stats: { intersectionCount: policyStatements[0]!.length, duplicatesRemoved: 0 },
      conflicts: [],
    };
  }

  const conflicts: PolicyConflict[] = [];
  const policyCount = policyStatements.length;

  // Map: resourceActionKey → array of statements from different policies
  const raMap = new Map<string, PolicyStatement[]>();
  for (const stmts of policyStatements) {
    for (const stmt of stmts) {
      const key = resourceActionKey(stmt);
      if (!raMap.has(key)) {
        raMap.set(key, []);
      }
      raMap.get(key)!.push(stmt);
    }
  }

  const result: PolicyStatement[] = [];
  let duplicatesRemoved = 0;

  for (const [key, stmts] of raMap.entries()) {
    // Check if this resource+action appears in ALL policies
