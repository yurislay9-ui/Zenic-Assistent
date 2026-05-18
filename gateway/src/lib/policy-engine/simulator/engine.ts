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
