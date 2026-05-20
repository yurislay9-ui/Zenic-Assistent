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
