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
