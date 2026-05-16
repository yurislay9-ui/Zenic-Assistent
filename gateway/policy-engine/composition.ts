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
    const policiesWithKey = new Set<string>();
    for (const stmt of stmts) {
      // We just need to count unique policy sources
      policiesWithKey.add(stmt.id.split("-")[0] ?? key);
    }

    // Actually, we need to check how many of the policy arrays contain at least one stmt with this key
    let policyCoverage = 0;
    for (const policyStmts of policyStatements) {
      if (policyStmts.some((s) => resourceActionKey(s) === key)) {
        policyCoverage++;
      }
    }

    if (policyCoverage < policyCount) {
      // Not present in all policies → skip
      duplicatesRemoved += stmts.length;
      continue;
    }

    // Present in all policies — check for effect conflicts
    const uniqueEffects = new Set(stmts.map((s) => s.effect));
    if (uniqueEffects.size === 1) {
      // All same effect → take the highest priority one
      const best = stmts.sort((a, b) => b.priority - a.priority)[0]!;
      result.push(best);
      duplicatesRemoved += stmts.length - 1;
    } else {
      // Different effects → deny wins
      const denyStmt = stmts.find((s) => s.effect === "deny");
      const best = denyStmt ?? stmts.sort((a, b) => b.priority - a.priority)[0]!;

      // Record conflict
      const effectGroups = new Map<string, PolicyStatement[]>();
      for (const s of stmts) {
        if (!effectGroups.has(s.effect)) effectGroups.set(s.effect, []);
        effectGroups.get(s.effect)!.push(s);
      }

      const effectEntries = [...effectGroups.entries()];
      if (effectEntries.length >= 2) {
        const groupA = effectEntries[0]!;
        const groupB = effectEntries[1]!;
        conflicts.push({
          id: `conflict_intersection_${key.replace(/[^a-zA-Z0-9]/g, "_")}`,
          type: "effect_contradiction" as ConflictType,
          severity: "critical" as ConflictSeverity,
          statementA: {
            policyId: "composed",
            version: "1.0.0",
            statementId: groupA[1][0]!.id,
            effect: groupA[1][0]!.effect,
            resource: groupA[1][0]!.resource,
            action: groupA[1][0]!.action,
          } as ConflictStatementRef,
          statementB: {
            policyId: "composed",
            version: "1.0.0",
            statementId: groupB[1][0]!.id,
            effect: groupB[1][0]!.effect,
            resource: groupB[1][0]!.resource,
            action: groupB[1][0]!.action,
          } as ConflictStatementRef,
          description: `INTERSECTION: resource+action "${key}" has conflicting effects (${[...uniqueEffects].join(", ")}), deny wins`,
          suggestedResolution: "deny_wins" as ConflictResolutionStrategy,
          resolved: true,
        });
      }

      result.push(best);
      duplicatesRemoved += stmts.length - 1;
    }
  }

  result.sort((a, b) => b.priority - a.priority);

  return {
    statements: result,
    stats: {
      intersectionCount: result.length,
      duplicatesRemoved,
    },
    conflicts,
  };
}

// ─── Merge Strategy: OVERRIDE ─────────────────────────────────────────

/**
 * OVERRIDE merge: Process policies in set entry order.
 * If a statement with the same ID exists in a later policy, replace it.
 * New statements from later policies are added.
 */
function mergeOverride(
  policyStatements: PolicyStatement[][],
): { statements: PolicyStatement[]; stats: Pick<CompositionStats, "overrideCount" | "duplicatesRemoved"> } {
  const statementMap = new Map<string, PolicyStatement>();
  let overrideCount = 0;
  let duplicatesRemoved = 0;

  for (const stmts of policyStatements) {
    for (const stmt of stmts) {
      if (statementMap.has(stmt.id)) {
        // Override existing statement
        statementMap.set(stmt.id, stmt);
        overrideCount++;
        duplicatesRemoved++;
      } else {
        statementMap.set(stmt.id, stmt);
      }
    }
  }

  const statements = [...statementMap.values()].sort((a, b) => b.priority - a.priority);

  return {
    statements,
    stats: {
      overrideCount,
      duplicatesRemoved,
    },
  };
}

// ─── Merge Strategy: EXTEND ───────────────────────────────────────────

/**
 * EXTEND merge: Start with the first policy.
 * Add statements from subsequent policies only if they don't conflict.
 * Never remove existing statements.
 * A conflict = same resource+action with different effect.
 */
function mergeExtend(
  policyStatements: PolicyStatement[][],
): { statements: PolicyStatement[]; stats: Pick<CompositionStats, "duplicatesRemoved">; conflicts: PolicyConflict[] } {
  if (policyStatements.length === 0) {
    return { statements: [], stats: { duplicatesRemoved: 0 }, conflicts: [] };
  }

  const conflicts: PolicyConflict[] = [];
  const result: PolicyStatement[] = [...policyStatements[0]!];
  let duplicatesRemoved = 0;

  // Build a lookup from the first policy
  const existingRA = new Map<string, PolicyStatement>();
  const existingIds = new Set<string>();
  for (const stmt of result) {
    existingRA.set(resourceActionKey(stmt), stmt);
    existingIds.add(stmt.id);
  }

  // Process subsequent policies
  for (let pi = 1; pi < policyStatements.length; pi++) {
    const stmts = policyStatements[pi]!;
    for (const stmt of stmts) {
      const raKey = resourceActionKey(stmt);

      if (existingIds.has(stmt.id)) {
        // Same ID already exists — don't remove/replace
        duplicatesRemoved++;
        continue;
      }

      const existing = existingRA.get(raKey);
      if (existing && existing.effect !== stmt.effect) {
        // Conflict: same resource+action but different effect — skip new statement
        duplicatesRemoved++;
        conflicts.push({
          id: `conflict_extend_${raKey.replace(/[^a-zA-Z0-9]/g, "_")}_p${pi}`,
          type: "effect_contradiction" as ConflictType,
          severity: "high" as ConflictSeverity,
          statementA: {
            policyId: "composed",
            version: "1.0.0",
            statementId: existing.id,
            effect: existing.effect,
            resource: existing.resource,
            action: existing.action,
          } as ConflictStatementRef,
          statementB: {
            policyId: "composed",
            version: "1.0.0",
            statementId: stmt.id,
            effect: stmt.effect,
            resource: stmt.resource,
            action: stmt.action,
          } as ConflictStatementRef,
          description: `EXTEND: resource+action "${raKey}" conflict — existing "${existing.effect}" blocks new "${stmt.effect}" from statement "${stmt.id}"`,
          suggestedResolution: "first_match" as ConflictResolutionStrategy,
          resolved: true,
        });
        continue;
      }

      // No conflict — add the new statement
      result.push(stmt);
      existingRA.set(raKey, stmt);
      existingIds.add(stmt.id);
    }
  }

  result.sort((a, b) => b.priority - a.priority);

  return {
    statements: result,
    stats: { duplicatesRemoved },
    conflicts,
  };
}

// ─── Merge Strategy: PRIORITY_MERGE ───────────────────────────────────

/**
 * PRIORITY_MERGE merge: Collect all statements, sort by priority (highest first).
 * On same priority with different effects: deny wins.
 * Build a merged document with the result.
 */
function mergePriorityMerge(
  policyStatements: PolicyStatement[][],
): { statements: PolicyStatement[]; stats: Pick<CompositionStats, "duplicatesRemoved">; conflicts: PolicyConflict[] } {
  const allStatements: PolicyStatement[] = [];
  for (const stmts of policyStatements) {
    allStatements.push(...stmts);
  }

  // Sort by priority (highest first), deny wins on same priority
  allStatements.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    return (EFFECT_ORDER[a.effect] ?? 3) - (EFFECT_ORDER[b.effect] ?? 3);
  });

  // Detect conflicts on same priority with different effects for same resource+action
  const conflicts: PolicyConflict[] = [];
  const priorityRAMap = new Map<string, PolicyStatement[]>();

  for (const stmt of allStatements) {
    const key = `${stmt.priority}::${resourceActionKey(stmt)}`;
    if (!priorityRAMap.has(key)) {
      priorityRAMap.set(key, []);
    }
    priorityRAMap.get(key)!.push(stmt);
  }

  for (const [key, stmts] of priorityRAMap.entries()) {
    if (stmts.length > 1) {
      const uniqueEffects = new Set(stmts.map((s) => s.effect));
      if (uniqueEffects.size > 1) {
        const [prioStr, ...raParts] = key.split("::");
        const raKey = raParts.join("::");
        const groupA = stmts[0]!;
        const groupB = stmts[1]!;
        conflicts.push({
          id: `conflict_pmerge_${prioStr}_${raKey.replace(/[^a-zA-Z0-9]/g, "_")}`,
          type: "priority_collision" as ConflictType,
          severity: "high" as ConflictSeverity,
          statementA: {
            policyId: "composed",
            version: "1.0.0",
            statementId: groupA.id,
            effect: groupA.effect,
            resource: groupA.resource,
            action: groupA.action,
          } as ConflictStatementRef,
          statementB: {
            policyId: "composed",
            version: "1.0.0",
            statementId: groupB.id,
            effect: groupB.effect,
            resource: groupB.resource,
            action: groupB.action,
          } as ConflictStatementRef,
          description: `PRIORITY_MERGE: priority ${prioStr} resource+action "${raKey}" has conflicting effects (${[...uniqueEffects].join(", ")}), deny wins`,
          suggestedResolution: "deny_wins" as ConflictResolutionStrategy,
          resolved: true,
        });
      }
    }
  }

  // Deduplicate by statement ID (keep first occurrence = highest priority / deny wins)
  const seen = new Map<string, PolicyStatement>();
  let duplicatesRemoved = 0;
  for (const stmt of allStatements) {
    if (seen.has(stmt.id)) {
      duplicatesRemoved++;
    } else {
      seen.set(stmt.id, stmt);
    }
  }

  const statements = [...seen.values()];

  return {
    statements,
    stats: { duplicatesRemoved },
    conflicts,
  };
}

// ─── Merged Document Builder ──────────────────────────────────────────

/**
 * Build a merged PolicyDocument from composed statements.
 * Builder pattern for constructing the final document.
 */
function buildMergedDocument(
  setId: string,
  setName: string,
  setDescription: string,
  statements: PolicyStatement[],
  namespace?: string,
): PolicyDocument {
  return {
    apiVersion: "policy.zenic.dev/v1",
    kind: "PolicyDocument",
    metadata: {
      id: `composed-${setId}`,
      name: `Composed: ${setName}`,
      version: "1.0.0",
      description: `Composed document from policy set "${setId}": ${setDescription}`,
      labels: {
        "zenic.dev/composed": "true",
        "zenic.dev/set-id": setId,
        ...(namespace ? { "zenic.dev/namespace": namespace } : {}),
      },
      author: "composition-engine",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
    statements,
  };
}

// ─── Composition Engine ───────────────────────────────────────────────

export class CompositionEngine {
  /**
   * Create a new policy set in the DB.
   * Validates all referenced policy IDs exist in DeclPolicy table.
   * Computes content hash and stores as PolicySet.
   */
  async createPolicySet(set: PolicySet): Promise<PolicySet> {
    // Validate apiVersion and kind
    if (set.apiVersion !== POLICY_SET_API_VERSION) {
      throw new Error(
        `Invalid apiVersion "${set.apiVersion}". Expected "${POLICY_SET_API_VERSION}"`,
      );
    }
    if (set.kind !== POLICY_SET_KIND) {
      throw new Error(
        `Invalid kind "${set.kind}". Expected "${POLICY_SET_KIND}"`,
      );
    }

    // Validate merge strategy
    if (!VALID_MERGE_STRATEGIES.has(set.defaultMergeStrategy)) {
      throw new Error(
        `Invalid merge strategy "${set.defaultMergeStrategy}". Must be one of: ${[...VALID_MERGE_STRATEGIES].join(", ")}`,
      );
    }

    // Validate metadata
    if (!set.metadata.id || typeof set.metadata.id !== "string") {
      throw new Error("metadata.id is required and must be a string");
    }
    if (!set.metadata.name || typeof set.metadata.name !== "string") {
      throw new Error("metadata.name is required and must be a string");
    }

    // Validate all referenced policy IDs exist
    const policyIds = set.policies.map((e) => e.policyId);
    if (policyIds.length > 0) {
      const existingPolicies = await db.declPolicy.findMany({
        where: {
          policyId: { in: policyIds },
          isActive: true,
        },
        select: { policyId: true },
      });
      const existingIds = new Set(existingPolicies.map((p) => p.policyId));

      const missing = policyIds.filter((id) => !existingIds.has(id));
      if (missing.length > 0) {
        // Check if any missing policies are marked as required
        const missingRequired = set.policies.filter(
          (e) => missing.includes(e.policyId) && e.required,
        );
        if (missingRequired.length > 0) {
          throw new Error(
            `Required policies not found: ${missingRequired.map((e) => e.policyId).join(", ")}`,
          );
        }
      }
    }

    // Check for duplicate setId
    const existing = await db.policySet.findUnique({
      where: { setId: set.metadata.id },
    });
    if (existing) {
      throw new Error(
        `PolicySet with setId "${set.metadata.id}" already exists`,
      );
    }

    // Compute content hash
    const canonicalPayload = {
      apiVersion: set.apiVersion,
      kind: set.kind,
      metadata: set.metadata,
      policies: set.policies,
      defaultMergeStrategy: set.defaultMergeStrategy,
      denyStopsEvaluation: set.denyStopsEvaluation,
    };
    const contentHash = createHash("sha256")
      .update(JSON.stringify(canonicalPayload, Object.keys(canonicalPayload).sort(), 2))
      .digest("hex");

    // Store in DB
    await db.policySet.create({
      data: {
        setId: set.metadata.id,
        name: set.metadata.name,
        description: set.metadata.description,
        apiVersion: set.apiVersion,
        version: set.metadata.version,
        namespace: set.metadata.namespace ?? null,
        labels: JSON.stringify(set.metadata.labels ?? {}),
        policies: JSON.stringify(set.policies),
        defaultMergeStrategy: set.defaultMergeStrategy,
        denyStopsEvaluation: set.denyStopsEvaluation,
        isActive: true,
        contentHash,
        author: set.metadata.author ?? null,
      },
    });

    return set;
  }

  /**
   * Load a policy set from DB by setId.
   */
  async getPolicySet(setId: string): Promise<PolicySet | null> {
    const record = await db.policySet.findUnique({
      where: { setId },
    });

    if (!record) return null;

    return this.mapRecordToPolicySet(record);
  }

  /**
   * List all policy sets, optionally filtered by namespace.
   */
  async listPolicySets(namespace?: string): Promise<PolicySet[]> {
    const where: Record<string, unknown> = { isActive: true };
    if (namespace !== undefined) {
      where.namespace = namespace;
    }

    const records = await db.policySet.findMany({
      where,
      orderBy: { createdAt: "desc" },
    });

    return records.map((r) => this.mapRecordToPolicySet(r));
  }

  /**
   * Compose all policies in a set using the merge strategy.
   * Returns ComposedPolicyResult with merged document, stats, and any conflicts.
   */
  async composePolicySet(setId: string): Promise<ComposedPolicyResult> {
    const startTime = Date.now();

    // Load the policy set
    const policySet = await this.getPolicySet(setId);
    if (!policySet) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    if (policySet.policies.length === 0) {
      return {
        setId,
        policyCount: 0,
        totalStatements: 0,
        byEffect: { allow: 0, deny: 0, conditional: 0 },
        conflicts: [],
        mergedDocument: buildMergedDocument(
          setId,
          policySet.metadata.name,
          policySet.metadata.description,
          [],
          policySet.metadata.namespace,
        ),
        stats: {
          unionCount: 0,
          intersectionCount: 0,
          overrideCount: 0,
          duplicatesRemoved: 0,
          mergeDuration: Date.now() - startTime,
        },
      };
    }

    // Load all referenced policies from DB
    const policyDocuments: PolicyDocument[] = [];
    const policyStatementArrays: PolicyStatement[][] = [];

    for (const entry of policySet.policies) {
      const declPolicy = await db.declPolicy.findFirst({
        where: {
          policyId: entry.policyId,
          isActive: true,
          ...(entry.version ? { version: entry.version } : {}),
        },
      });

      if (!declPolicy) {
        if (entry.required) {
          throw new Error(
            `Required policy "${entry.policyId}"${entry.version ? ` version "${entry.version}"` : ""} not found in DB`,
          );
        }
        // Non-required missing policy — skip
        continue;
      }

      const doc: PolicyDocument = {
        apiVersion: declPolicy.apiVersion as typeof import("./types").POLICY_API_VERSION,
        kind: "PolicyDocument",
        metadata: {
          id: declPolicy.policyId,
          name: declPolicy.name,
          version: declPolicy.version,
          description: declPolicy.description,
          compliance: JSON.parse(declPolicy.compliance),
          labels: JSON.parse(declPolicy.labels),
          author: declPolicy.author ?? undefined,
          createdAt: declPolicy.createdAt.toISOString(),
          updatedAt: declPolicy.updatedAt.toISOString(),
        },
        statements: JSON.parse(declPolicy.statements),
        tests: JSON.parse(declPolicy.tests),
      };

      // Apply overrides if specified on the entry
      let finalStatements = doc.statements;
      if (entry.overrides && entry.overrides.length > 0) {
        finalStatements = this.applyOverrides(doc.statements, entry.overrides);
      }

      policyDocuments.push({ ...doc, statements: finalStatements });
      policyStatementArrays.push(finalStatements);
    }

    // Determine the merge strategy (use entry override or set default)
    const mergeStrategy = policySet.defaultMergeStrategy;

    // Apply merge strategy
    let mergedStatements: PolicyStatement[];
    let stats: Partial<CompositionStats>;
    let conflicts: PolicyConflict[] = [];

    switch (mergeStrategy) {
      case "union": {
        const result = mergeUnion(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        break;
      }
      case "intersection": {
        const result = mergeIntersection(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        conflicts = result.conflicts;
        break;
      }
      case "override": {
        const result = mergeOverride(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        break;
      }
      case "extend": {
        const result = mergeExtend(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        conflicts = result.conflicts;
        break;
      }
      case "priority_merge": {
        const result = mergePriorityMerge(policyStatementArrays);
        mergedStatements = result.statements;
        stats = result.stats;
        conflicts = result.conflicts;
        break;
      }
      default:
        throw new Error(`Unknown merge strategy: ${mergeStrategy}`);
    }

    const mergeDuration = Date.now() - startTime;

    // Compute byEffect counts
    const byEffect: Record<PolicyEffectV2, number> = {
      allow: 0,
      deny: 0,
      conditional: 0,
    };
    for (const stmt of mergedStatements) {
      byEffect[stmt.effect] = (byEffect[stmt.effect] ?? 0) + 1;
    }

    // Build merged document
    const mergedDocument = buildMergedDocument(
      setId,
      policySet.metadata.name,
      policySet.metadata.description,
      mergedStatements,
      policySet.metadata.namespace,
    );

    // Compute content hash of the merged document for integrity tracking
    const mergedContentHash = computeContentHash(mergedDocument);
    mergedDocument.metadata.labels = {
      ...mergedDocument.metadata.labels,
      "zenic.dev/content-hash": mergedContentHash,
    };

    return {
      setId,
      policyCount: policyDocuments.length,
      totalStatements: mergedStatements.length,
      byEffect,
      conflicts,
      mergedDocument,
      stats: {
        unionCount: stats.unionCount ?? 0,
        intersectionCount: stats.intersectionCount ?? 0,
        overrideCount: stats.overrideCount ?? 0,
        duplicatesRemoved: stats.duplicatesRemoved ?? 0,
        mergeDuration,
      },
    };
  }

  /**
   * Add a policy entry to an existing set.
   */
  async addPolicyToSet(setId: string, entry: PolicySetEntry): Promise<PolicySet> {
    // Validate the policy exists
    const policyExists = await db.declPolicy.findFirst({
      where: {
        policyId: entry.policyId,
        isActive: true,
        ...(entry.version ? { version: entry.version } : {}),
      },
    });

    if (!policyExists && entry.required) {
      throw new Error(
        `Required policy "${entry.policyId}"${entry.version ? ` version "${entry.version}"` : ""} not found`,
      );
    }

    // Load current set
    const current = await db.policySet.findUnique({
      where: { setId },
    });

    if (!current) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    // Parse current policies
    const policies: PolicySetEntry[] = JSON.parse(current.policies);

    // Check for duplicate entry
    const alreadyExists = policies.some(
      (p) => p.policyId === entry.policyId && p.version === entry.version,
    );
    if (alreadyExists) {
      throw new Error(
        `Policy "${entry.policyId}"${entry.version ? ` version "${entry.version}"` : ""} already in set "${setId}"`,
      );
    }

    // Add the new entry
    policies.push(entry);

    // Recompute content hash
    const setObj = this.mapRecordToPolicySet({ ...current, policies: JSON.stringify(policies) });
    const contentHash = this.computeSetContentHash(setObj);

    // Update in DB
    await db.policySet.update({
      where: { setId },
      data: {
        policies: JSON.stringify(policies),
        contentHash,
      },
    });

    return setObj;
  }

  /**
   * Remove a policy entry from a set.
   */
  async removePolicyFromSet(setId: string, policyId: string): Promise<PolicySet> {
    // Load current set
    const current = await db.policySet.findUnique({
      where: { setId },
    });

    if (!current) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    // Parse and filter
    const policies: PolicySetEntry[] = JSON.parse(current.policies);
    const filtered = policies.filter((p) => p.policyId !== policyId);

    if (filtered.length === policies.length) {
      throw new Error(
        `Policy "${policyId}" not found in set "${setId}"`,
      );
    }

    // Recompute content hash
    const setObj = this.mapRecordToPolicySet({ ...current, policies: JSON.stringify(filtered) });
    const contentHash = this.computeSetContentHash(setObj);

    // Update in DB
    await db.policySet.update({
      where: { setId },
      data: {
        policies: JSON.stringify(filtered),
        contentHash,
      },
    });

    return setObj;
  }

  /**
   * Delete a policy set.
   */
  async deletePolicySet(setId: string): Promise<void> {
    const existing = await db.policySet.findUnique({
      where: { setId },
    });

    if (!existing) {
      throw new Error(`PolicySet "${setId}" not found`);
    }

    await db.policySet.delete({
      where: { setId },
    });
  }

  // ─── Internal Helpers ──────────────────────────────────────────────────

  /**
   * Map a DB record to a PolicySet type.
   */
  private mapRecordToPolicySet(record: {
    setId: string;
    name: string;
    description: string;
    apiVersion: string;
    version: string;
    namespace: string | null;
    labels: string;
    policies: string;
    defaultMergeStrategy: string;
    denyStopsEvaluation: boolean;
    isActive: boolean;
    contentHash: string;
    author: string | null;
    createdAt: Date;
    updatedAt: Date;
  }): PolicySet {
    return {
      apiVersion: record.apiVersion as typeof POLICY_SET_API_VERSION,
      kind: POLICY_SET_KIND,
      metadata: {
        id: record.setId,
        name: record.name,
        version: record.version,
        description: record.description,
        namespace: record.namespace ?? undefined,
        labels: JSON.parse(record.labels),
        author: record.author ?? undefined,
        createdAt: record.createdAt.toISOString(),
        updatedAt: record.updatedAt.toISOString(),
      },
      policies: JSON.parse(record.policies),
      defaultMergeStrategy: record.defaultMergeStrategy as MergeStrategy,
      denyStopsEvaluation: record.denyStopsEvaluation,
    };
  }

  /**
   * Compute content hash for a PolicySet.
   */
  private computeSetContentHash(set: PolicySet): string {
    const canonicalPayload = {
      apiVersion: set.apiVersion,
      kind: set.kind,
      metadata: set.metadata,
      policies: set.policies,
      defaultMergeStrategy: set.defaultMergeStrategy,
      denyStopsEvaluation: set.denyStopsEvaluation,
    };
    return createHash("sha256")
      .update(JSON.stringify(canonicalPayload, Object.keys(canonicalPayload).sort(), 2))
      .digest("hex");
  }

  /**
   * Apply partial overrides to statements.
   */
  private applyOverrides(
    statements: PolicyStatement[],
    overrides: Partial<PolicyStatement>[],
  ): PolicyStatement[] {
    const result = statements.map((stmt) => {
      const matchingOverride = overrides.find((o) => o.id === stmt.id);
      if (matchingOverride) {
        return { ...stmt, ...matchingOverride } as PolicyStatement;
      }
      return stmt;
    });

    // Add new statements from overrides that don't match existing IDs
    const existingIds = new Set(statements.map((s) => s.id));
    for (const override of overrides) {
      if (override.id && !existingIds.has(override.id)) {
        result.push(override as PolicyStatement);
      }
    }

    return result;
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let engineInstance: CompositionEngine | null = null;

/**
 * Get the singleton CompositionEngine instance.
 */
export function getCompositionEngine(): CompositionEngine {
  if (!engineInstance) {
    engineInstance = new CompositionEngine();
  }
  return engineInstance;
}

/**
 * Reset the singleton CompositionEngine instance.
 */
export function resetCompositionEngine(): void {
  engineInstance = null;
}
