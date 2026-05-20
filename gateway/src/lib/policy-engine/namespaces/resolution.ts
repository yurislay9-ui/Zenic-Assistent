): Promise<{ result: PolicyEvaluationResult; trace: NamespaceEvaluationTrace[] }> {
  // Evaluate local namespace policies
  const localPolicies = await loadNamespacePolicies(namespaceRec.namespaceId, namespaceRec.tenantId);

  let localResult: PolicyEvaluationResult | null = null;

  for (const policy of localPolicies) {
    const evalResult = evaluator.evaluateDocument(policy, request);
    if (evalResult.effect !== "deny" || !evalResult.denyByDefault) {
      // We got a definitive result from this policy
      if (!localResult || isMoreRestrictive(evalResult.effect, localResult.effect)) {
        localResult = evalResult;
      }
      // If we got a deny, it's definitive — stop
      if (evalResult.effect === "deny") break;
    }
  }

  trace.push({
    namespaceId: namespaceRec.namespaceId,
    namespacePath: namespaceRec.path,
    depth,
    policiesEvaluated: localPolicies.length,
    result: localResult,
    inherited: false,
  });

  // If we have a definitive local result, apply hierarchy constraints and return
  if (localResult && !localResult.denyByDefault) {
    // Check if parent should be consulted for constraints
    if (
      namespaceRec.inheritFromParent &&
      namespaceRec.parentNamespaceId &&
      depth < namespaceRec.maxInheritanceDepth
    ) {
      const parentRec = await loadNamespaceRecord(namespaceRec.parentNamespaceId);
      if (parentRec && parentRec.isActive) {
        const parentPolicies = await loadNamespacePolicies(parentRec.namespaceId, parentRec.tenantId);
        let parentResult: PolicyEvaluationResult | null = null;
        for (const policy of parentPolicies) {
          const evalResult = evaluator.evaluateDocument(policy, request);
          if (!evalResult.denyByDefault) {
            if (!parentResult || isMoreRestrictive(evalResult.effect, parentResult.effect)) {
              parentResult = evalResult;
            }
            if (evalResult.effect === "deny") break;
          }
        }

        trace.push({
          namespaceId: parentRec.namespaceId,
          namespacePath: parentRec.path,
          depth: depth + 1,
          policiesEvaluated: parentPolicies.length,
          result: parentResult,
          inherited: true,
        });

        if (parentResult && !parentResult.denyByDefault) {
          // Apply parent-child constraints
          const constrained = applyParentChildConstraints(
            localResult,
            parentResult,
            mapRecordToPolicyNamespace(namespaceRec).hierarchy,
          );
          return { result: constrained, trace };
        }
      }
    }
    return { result: localResult, trace };
  }

  // No definitive local result — walk up to parent (Chain of Responsibility)
  if (
    namespaceRec.inheritFromParent &&
    namespaceRec.parentNamespaceId &&
    depth < namespaceRec.maxInheritanceDepth
  ) {
    const parentRec = await loadNamespaceRecord(namespaceRec.parentNamespaceId);
    if (parentRec && parentRec.isActive) {
      const parentOutcome = await evaluateLocalFirst(request, parentRec, evaluator, trace, depth + 1);
      if (parentOutcome.result && !parentOutcome.result.denyByDefault) {
        // Apply parent-child resolution
        const resolved = resolveParentChildConflict(
          localResult ?? parentOutcome.result,
          parentOutcome.result,
          mapRecordToPolicyNamespace(namespaceRec).hierarchy,
        );
        return { result: resolved, trace: parentOutcome.trace };
      }
    }
  }

  // No result from anywhere — return deny-by-default
  return {
    result: {
      effect: "deny",
      policyId: "default",
      reason: "No matching policy in namespace hierarchy — default deny applied",
      matchedStatements: [],
      duration: 0,
      denyByDefault: true,
    },
    trace,
  };
}

/**
 * PRIORITY_BASED strategy: Collect statements from all namespaces
 * in hierarchy, sort by priority, evaluate top match.
 */
async function evaluatePriorityBased(
  request: PolicyEvaluationRequest,
  namespaceRec: NamespaceDbRecord,
  evaluator: PolicyEvaluator,
  trace: NamespaceEvaluationTrace[],
): Promise<{ result: PolicyEvaluationResult; trace: NamespaceEvaluationTrace[] }> {
  // Collect all policies from the full hierarchy
  const allPolicies: Array<{ policy: PolicyDocument; namespaceId: string; depth: number }> = [];
  const visited = new Set<string>();
  const queue: Array<{ nsId: string; depth: number }> = [{ nsId: namespaceRec.namespaceId, depth: 0 }];

  while (queue.length > 0) {
    const item = queue.shift()!;
    if (visited.has(item.nsId)) continue;
    visited.add(item.nsId);

    const rec = await loadNamespaceRecord(item.nsId);
    if (!rec || !rec.isActive) continue;

    // Check depth limit
    if (item.depth > rec.maxInheritanceDepth) continue;

    const policies = await loadNamespacePolicies(rec.namespaceId, rec.tenantId);
    for (const policy of policies) {
      allPolicies.push({ policy, namespaceId: rec.namespaceId, depth: item.depth });
    }

    trace.push({
      namespaceId: rec.namespaceId,
      namespacePath: rec.path,
      depth: item.depth,
      policiesEvaluated: policies.length,
      result: null,
      inherited: item.depth > 0,
    });

    // Walk up to parent if inheritance is enabled
    if (rec.inheritFromParent && rec.parentNamespaceId) {
      queue.push({ nsId: rec.parentNamespaceId, depth: item.depth + 1 });
    }
  }

  // Collect all matching statements across all policies
  const allMatched: Array<{
    policyId: string;
    statementId: string;
    effect: PolicyEffectV2;
    priority: number;
    namespaceId: string;
    depth: number;
  }> = [];

  for (const { policy, namespaceId, depth } of allPolicies) {
    for (const statement of policy.statements) {
      if (statementMatchesRequest(statement, request)) {
        allMatched.push({
          policyId: policy.metadata.id,
          statementId: statement.id,
          effect: statement.effect,
          priority: statement.priority,
          namespaceId,
          depth,
        });
      }
    }
  }

  // Sort by priority (highest first), deny wins on tie
  allMatched.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    const effectOrder: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };
    return (effectOrder[a.effect] ?? 3) - (effectOrder[b.effect] ?? 3);
  });

  if (allMatched.length === 0) {
    return {
      result: {
        effect: "deny",
        policyId: "default",
        reason: "No matching statement in any namespace — default deny applied",
        matchedStatements: [],
        duration: 0,
        denyByDefault: true,
      },
      trace,
    };
  }

  const topMatch = allMatched[0]!;
  return {
    result: {
      effect: topMatch.effect,
      policyId: topMatch.policyId,
      matchedStatementId: topMatch.statementId,
      reason: `PRIORITY_BASED: matched statement "${topMatch.statementId}" in policy "${topMatch.policyId}" (namespace: ${topMatch.namespaceId}, priority: ${topMatch.priority})`,
      matchedStatements: allMatched.map((m) => ({
        policyId: m.policyId,
        statementId: m.statementId,
        effect: m.effect,
        priority: m.priority,
      })),
      duration: 0,
      denyByDefault: false,
    },
    trace,
  };
}

/**
 * DENY_WINS strategy: If ANY namespace in the hierarchy returns DENY, the final result is DENY.
 */
async function evaluateDenyWins(
  request: PolicyEvaluationRequest,
  namespaceRec: NamespaceDbRecord,
  evaluator: PolicyEvaluator,
  trace: NamespaceEvaluationTrace[],
): Promise<{ result: PolicyEvaluationResult; trace: NamespaceEvaluationTrace[] }> {
  const results: Array<{
    result: PolicyEvaluationResult;
    namespaceId: string;
    depth: number;
  }> = [];

  // Walk the full hierarchy
  const visited = new Set<string>();
  const queue: Array<{ nsId: string; depth: number }> = [{ nsId: namespaceRec.namespaceId, depth: 0 }];

  while (queue.length > 0) {
    const item = queue.shift()!;
    if (visited.has(item.nsId)) continue;
    visited.add(item.nsId);

    const rec = await loadNamespaceRecord(item.nsId);
    if (!rec || !rec.isActive) continue;
    if (item.depth > rec.maxInheritanceDepth) continue;

    const policies = await loadNamespacePolicies(rec.namespaceId, rec.tenantId);

    let nsResult: PolicyEvaluationResult | null = null;
    for (const policy of policies) {
      const evalResult = evaluator.evaluateDocument(policy, request);
      if (!evalResult.denyByDefault) {
        if (!nsResult || isMoreRestrictive(evalResult.effect, nsResult.effect)) {
          nsResult = evalResult;
        }
        if (evalResult.effect === "deny") break;
      }
    }

    trace.push({
      namespaceId: rec.namespaceId,
      namespacePath: rec.path,
      depth: item.depth,
      policiesEvaluated: policies.length,
      result: nsResult,
      inherited: item.depth > 0,
    });

    if (nsResult) {
      results.push({ result: nsResult, namespaceId: rec.namespaceId, depth: item.depth });
    }

    if (rec.inheritFromParent && rec.parentNamespaceId) {
      queue.push({ nsId: rec.parentNamespaceId, depth: item.depth + 1 });
    }
  }

  // DENY_WINS: If any namespace returns DENY, final result is DENY
  const denyResult = results.find((r) => r.result.effect === "deny");
  if (denyResult) {
    return {
      result: {
        ...denyResult.result,
        reason: `DENY_WINS: namespace "${denyResult.namespaceId}" returned DENY — ${denyResult.result.reason}`,
        matchedStatements: results.flatMap((r) => r.result.matchedStatements),
      },
      trace,
    };
  }

  // No deny — return the most restrictive result from the closest namespace
  const closestResult = results.find((r) => r.depth === 0);
  if (closestResult) {
    return {
      result: {
        ...closestResult.result,
        reason: `DENY_WINS: no DENY found, closest result preserved — ${closestResult.result.reason}`,
        matchedStatements: results.flatMap((r) => r.result.matchedStatements),
      },
