 * List namespaces with optional filtering by tenant and/or parent.
 */
export async function listNamespaces(
  tenantId?: string,
  parentNamespaceId?: string,
): Promise<PolicyNamespace[]> {
  const where: Record<string, unknown> = { isActive: true };

  if (tenantId) {
    where.tenantId = tenantId;
  }
  if (parentNamespaceId !== undefined) {
    where.parentNamespaceId = parentNamespaceId ?? null;
  }

  const rows = await db.policyNamespace.findMany({
    where,
    orderBy: { path: "asc" },
  });

  return rows.map((row) => mapRecordToPolicyNamespace(mapDbToRecord(row)));
}

/**
 * Evaluate a request within a namespace context.
 *
 * Resolution algorithm:
 *   a. Find the namespace
 *   b. Get policies belonging to this namespace
 *   c. Evaluate request against local policies
 *   d. If inheritFromParent and no definitive result:
 *      - Walk up the namespace hierarchy
 *      - Evaluate against parent namespace policies
 *      - Apply parentChildResolution strategy
 *   e. Return NamespaceResolutionResult with full trace
 */
export async function evaluateInNamespace(
  request: PolicyEvaluationRequest,
  namespaceId: string,
): Promise<NamespaceResolutionResult> {
  const startTime = Date.now();

  // a. Find the namespace
  const namespaceRec = await loadNamespaceRecord(namespaceId);
  if (!namespaceRec) {
    throw new NamespaceError(
      `Namespace "${namespaceId}" not found`,
      "NAMESPACE_NOT_FOUND",
      { namespaceId },
    );
  }

  if (!namespaceRec.isActive) {
    throw new NamespaceError(
      `Namespace "${namespaceId}" is not active`,
      "NAMESPACE_INACTIVE",
      { namespaceId },
    );
  }

  const evaluator = getPolicyEvaluator();
  const trace: NamespaceEvaluationTrace[] = [];

  // Dispatch to the appropriate resolution strategy
  let evalResult: { result: PolicyEvaluationResult; trace: NamespaceEvaluationTrace[] };

  switch (namespaceRec.resolutionStrategy) {
    case ResolutionStrategy.LOCAL_FIRST:
      evalResult = await evaluateLocalFirst(request, namespaceRec, evaluator, trace, 0);
      break;

    case ResolutionStrategy.PRIORITY_BASED:
      evalResult = await evaluatePriorityBased(request, namespaceRec, evaluator, trace);
      break;

    case ResolutionStrategy.DENY_WINS:
      evalResult = await evaluateDenyWins(request, namespaceRec, evaluator, trace);
      break;

    case ResolutionStrategy.MOST_RESTRICTIVE:
      evalResult = await evaluateMostRestrictive(request, namespaceRec, evaluator, trace);
      break;

    default:
      // Default to LOCAL_FIRST
      evalResult = await evaluateLocalFirst(request, namespaceRec, evaluator, trace, 0);
      break;
  }

  // Build the inheritance chain from the trace
  const inheritanceChain = evalResult.trace
    .filter((t) => t.inherited || t.depth === 0)
    .map((t) => t.namespaceId);

  const consultedNamespaces = evalResult.trace.map((t) => t.namespaceId);
  const parentConsulted = evalResult.trace.some((t) => t.inherited);
  const inheritedRulesApplied = evalResult.trace.some(
    (t) => t.inherited && t.result && !t.result.denyByDefault,
  );

  const finalResult: PolicyEvaluationResult = {
    ...evalResult.result,
    duration: Date.now() - startTime,
  };

  return {
    resolvingNamespace: evalResult.trace.find((t) => t.depth === 0)?.namespaceId ?? namespaceId,
    consultedNamespaces,
    inheritanceChain,
    evaluation: finalResult,
    parentConsulted,
    inheritedRulesApplied,
  };
}

/**
 * Get the full hierarchy from root to the specified namespace.
 * Returns an ordered array starting from the root namespace down to this namespace.
 */
export async function getNamespaceHierarchy(namespaceId: string): Promise<PolicyNamespace[]> {
  const hierarchy: PolicyNamespace[] = [];

  let currentId: string | null = namespaceId;
  const visited = new Set<string>();

  // Walk up from the target namespace to the root
  const chain: NamespaceDbRecord[] = [];
  while (currentId) {
    if (visited.has(currentId)) break; // Circular reference guard
    visited.add(currentId);

    const rec = await loadNamespaceRecord(currentId);
    if (!rec) break;

    chain.push(rec);
    currentId = rec.parentNamespaceId;
  }

  // Reverse to get root-first order
  chain.reverse();

  for (const rec of chain) {
    hierarchy.push(mapRecordToPolicyNamespace(rec));
  }

  return hierarchy;
}

/**
 * Update a namespace's configuration.
 * Only the provided fields will be updated.
 */
export async function updateNamespace(
  namespaceId: string,
  updates: NamespaceUpdateRequest,
): Promise<PolicyNamespace> {
  const existing = await loadNamespaceRecord(namespaceId);
  if (!existing) {
    throw new NamespaceError(
      `Namespace "${namespaceId}" not found`,
      "NAMESPACE_NOT_FOUND",
      { namespaceId },
    );
  }

  if (!existing.isActive) {
    throw new NamespaceError(
      `Cannot update inactive namespace "${namespaceId}"`,
      "NAMESPACE_INACTIVE",
      { namespaceId },
    );
  }

  // Validate hierarchy changes
  if (updates.maxInheritanceDepth !== undefined) {
    const currentDepth = await computeDepth(namespaceId);
    if (updates.maxInheritanceDepth < currentDepth) {
      throw new NamespaceError(
        `Cannot set maxInheritanceDepth to ${updates.maxInheritanceDepth}: current depth is ${currentDepth}`,
        "INVALID_DEPTH",
        { namespaceId, currentDepth, proposedMax: updates.maxInheritanceDepth },
      );
    }
  }

  // Build update data
  const updateData: Record<string, unknown> = {};
  if (updates.name !== undefined) updateData.name = updates.name;
  if (updates.description !== undefined) updateData.description = updates.description;
  if (updates.labels !== undefined) updateData.labels = JSON.stringify(updates.labels);
  if (updates.inheritFromParent !== undefined) updateData.inheritFromParent = updates.inheritFromParent;
  if (updates.maxInheritanceDepth !== undefined) updateData.maxInheritanceDepth = updates.maxInheritanceDepth;
  if (updates.parentChildResolution !== undefined) updateData.parentChildResolution = updates.parentChildResolution;
  if (updates.childCanOverrideParentDeny !== undefined) updateData.childCanOverrideParentDeny = updates.childCanOverrideParentDeny;
  if (updates.childCanAddAllow !== undefined) updateData.childCanAddAllow = updates.childCanAddAllow;
  if (updates.resolutionStrategy !== undefined) updateData.resolutionStrategy = updates.resolutionStrategy;
  if (updates.isolationLevel !== undefined) updateData.isolationLevel = updates.isolationLevel;

  try {
    const row = await db.policyNamespace.update({
      where: { namespaceId },
      data: updateData,
    });

    return mapRecordToPolicyNamespace(mapDbToRecord(row));
  } catch (error) {
    throw new NamespaceError(
      `Failed to update namespace "${namespaceId}": ${error instanceof Error ? error.message : String(error)}`,
      "UPDATE_FAILED",
      { namespaceId },
    );
  }
}

/**
 * Delete (deactivate) a namespace.
 * This is a soft delete — the namespace is marked as inactive.
 * Child namespaces that reference this parent will still point to it,
 * but inheritance will stop at the deactivated namespace.
 */
export async function deleteNamespace(namespaceId: string): Promise<void> {
  const existing = await loadNamespaceRecord(namespaceId);
  if (!existing) {
    throw new NamespaceError(
      `Namespace "${namespaceId}" not found`,
      "NAMESPACE_NOT_FOUND",
      { namespaceId },
    );
  }

  if (!existing.isActive) {
    throw new NamespaceError(
      `Namespace "${namespaceId}" is already inactive`,
      "ALREADY_INACTIVE",
      { namespaceId },
    );
  }

  // Check for active child namespaces
  const children = await db.policyNamespace.findMany({
    where: {
      parentNamespaceId: namespaceId,
      isActive: true,
    },
  });

  try {
    await db.policyNamespace.update({
      where: { namespaceId },
      data: {
        isActive: false,
        labels: JSON.stringify({
          ...existing.labels,
          deactivatedAt: new Date().toISOString(),
          hadActiveChildren: children.length > 0,
          activeChildCount: children.length,
        }),
      },
    });
  } catch (error) {
    throw new NamespaceError(
      `Failed to deactivate namespace "${namespaceId}": ${error instanceof Error ? error.message : String(error)}`,
      "DELETE_FAILED",
      { namespaceId },
    );
  }
}
