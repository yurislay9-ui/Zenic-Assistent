      trace,
    };
  }

  return {
    result: {
      effect: "deny",
      policyId: "default",
      reason: "DENY_WINS: no policies matched in any namespace — default deny applied",
      matchedStatements: [],
      duration: 0,
      denyByDefault: true,
    },
    trace,
  };
}

/**
 * MOST_RESTRICTIVE strategy: Choose the most restrictive verdict across all namespaces.
 */
async function evaluateMostRestrictive(
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

  if (results.length === 0) {
    return {
      result: {
        effect: "deny",
        policyId: "default",
        reason: "MOST_RESTRICTIVE: no policies matched in any namespace — default deny applied",
        matchedStatements: [],
        duration: 0,
        denyByDefault: true,
      },
      trace,
    };
  }

  // Sort by restrictiveness (deny > conditional > allow) and pick the most restrictive
  results.sort((a, b) => {
    const aOrder = RESTRICTIVENESS_ORDER[a.result.effect] ?? 3;
    const bOrder = RESTRICTIVENESS_ORDER[b.result.effect] ?? 3;
    return aOrder - bOrder;
  });

  const mostRestrictiveResult = results[0]!;
  return {
    result: {
      ...mostRestrictiveResult.result,
      reason: `MOST_RESTRICTIVE: "${mostRestrictiveResult.namespaceId}" has most restrictive effect "${mostRestrictiveResult.result.effect}" — ${mostRestrictiveResult.result.reason}`,
      matchedStatements: results.flatMap((r) => r.result.matchedStatements),
    },
    trace,
  };
}

// ─── Helper: Check if a statement matches a request ───────────────────
// BUG #2 FIX: Import shared evaluation functions from evaluator instead of
// duplicating them. This ensures security fixes (e.g. ReDoS in regex) are
// applied everywhere. INVARIANT 4: defense in depth requires consistency.

// Re-export operator strategies and helpers from evaluator (single source of truth)
// We use dynamic import via require-style to avoid circular deps at module level.
// The evaluator exports these as module-level constants, so we reference them lazily.

// Lazy accessor: avoids circular import issues at module initialization
function getOperatorStrategies(): Record<string, (fieldValue: unknown, conditionValue: unknown) => boolean> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const evaluator = require("./evaluator");
  return evaluator.OPERATOR_STRATEGIES;
}

function matchesPattern(pattern: string, value: string): boolean {
  if (pattern === "*") return true;
  if (pattern === value) return true;
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    return value === prefix || value.startsWith(`${prefix}/`);
  }
  if (pattern.startsWith("*/")) {
    const suffix = pattern.slice(1);
    return value.endsWith(suffix);
  }
  return false;
}

function getNestedField(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    if (typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function statementMatchesRequest(
  statement: PolicyStatement,
  request: PolicyEvaluationRequest,
): boolean {
  if (!matchesPattern(statement.resource, request.resource)) return false;
  if (!matchesPattern(statement.action, request.action)) return false;

  if (statement.conditions && statement.conditions.length > 0) {
    const strategies = getOperatorStrategies();
    return statement.conditions.every((condition) => {
      const fieldValue = getNestedField(request.context, condition.field);
      const strategy = strategies[condition.operator];
      if (!strategy) return false;
      return strategy(fieldValue, condition.value);
    });
  }

  return true;
}

// ─── Helper: Load a namespace record from DB ──────────────────────────

async function loadNamespaceRecord(namespaceId: string): Promise<NamespaceDbRecord | null> {
  const row = await db.policyNamespace.findFirst({
    where: { namespaceId },
  });
  if (!row) return null;
  return mapDbToRecord(row);
}

// ─── Helper: Compute depth of a namespace in the hierarchy ────────────

async function computeDepth(namespaceId: string): Promise<number> {
  let depth = 0;
  let currentId: string | null | undefined = namespaceId;
  const visited = new Set<string>();

  while (currentId) {
    if (visited.has(currentId)) break; // Circular reference guard
    visited.add(currentId);

    const rec = await loadNamespaceRecord(currentId);
    if (!rec) break;
    currentId = rec.parentNamespaceId;
    if (currentId) depth++;
  }

  return depth;
}

// ═══════════════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════════════

/**
 * Create a new namespace.
 * Validates ID uniqueness, parent existence, and hierarchy depth.
 */
export async function createNamespace(ns: PolicyNamespace): Promise<PolicyNamespace> {
  const { metadata, hierarchy, resolutionStrategy, isolationLevel } = ns;

  // 1. Validate namespace ID uniqueness
  const existing = await db.policyNamespace.findFirst({
    where: { namespaceId: metadata.id },
  });
  if (existing) {
    throw new NamespaceError(
      `Namespace ID "${metadata.id}" already exists`,
      "DUPLICATE_NAMESPACE_ID",
      { namespaceId: metadata.id },
    );
  }

  // 2. Validate parent namespace exists (if specified)
  let parentPath = "";
  if (metadata.parentNamespaceId) {
    const parent = await loadNamespaceRecord(metadata.parentNamespaceId);
    if (!parent) {
      throw new NamespaceError(
        `Parent namespace "${metadata.parentNamespaceId}" does not exist`,
        "PARENT_NOT_FOUND",
        { parentNamespaceId: metadata.parentNamespaceId },
      );
    }
    if (!parent.isActive) {
      throw new NamespaceError(
        `Parent namespace "${metadata.parentNamespaceId}" is not active`,
        "PARENT_INACTIVE",
        { parentNamespaceId: metadata.parentNamespaceId },
      );
    }
    parentPath = parent.path;

    // 3. Validate hierarchy depth doesn't exceed maxInheritanceDepth
    const parentDepth = await computeDepth(metadata.parentNamespaceId);
    if (parentDepth + 1 >= hierarchy.maxInheritanceDepth) {
      throw new NamespaceError(
        `Creating namespace "${metadata.id}" would exceed maxInheritanceDepth of ${hierarchy.maxInheritanceDepth}`,
        "MAX_DEPTH_EXCEEDED",
        { parentNamespaceId: metadata.parentNamespaceId, currentDepth: parentDepth + 1, maxDepth: hierarchy.maxInheritanceDepth },
      );
    }
  }

  // 4. Build path from parent path + namespace ID
  const path = parentPath ? `${parentPath}/${metadata.id}` : metadata.id;

  // 5. Persist to PolicyNamespace table
  try {
    const row = await db.policyNamespace.create({
      data: {
        namespaceId: metadata.id,
        name: metadata.name,
        description: metadata.description,
        tenantId: metadata.tenantId,
        parentNamespaceId: metadata.parentNamespaceId ?? null,
        path,
        labels: JSON.stringify(metadata.labels ?? {}),
        inheritFromParent: hierarchy.inheritFromParent,
        maxInheritanceDepth: hierarchy.maxInheritanceDepth,
        parentChildResolution: hierarchy.parentChildResolution,
        childCanOverrideParentDeny: hierarchy.childCanOverrideParentDeny,
        childCanAddAllow: hierarchy.childCanAddAllow,
        resolutionStrategy,
        isolationLevel,
        isActive: true,
      },
    });

    return mapRecordToPolicyNamespace(mapDbToRecord(row));
  } catch (error) {
    throw new NamespaceError(
      `Failed to create namespace "${metadata.id}": ${error instanceof Error ? error.message : String(error)}`,
      "CREATE_FAILED",
      { namespaceId: metadata.id },
    );
  }
}

/**
 * Load a namespace from the database.
 */
export async function getNamespace(namespaceId: string): Promise<PolicyNamespace | null> {
  const rec = await loadNamespaceRecord(namespaceId);
  if (!rec) return null;
  return mapRecordToPolicyNamespace(rec);
}

/**
