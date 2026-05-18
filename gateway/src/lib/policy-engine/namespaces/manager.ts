      parentNamespaceId: rec.parentNamespaceId ?? undefined,
      path: rec.path,
      labels: rec.labels,
      createdAt: rec.createdAt.toISOString(),
      updatedAt: rec.updatedAt.toISOString(),
    },
    hierarchy: {
      inheritFromParent: rec.inheritFromParent,
      maxInheritanceDepth: rec.maxInheritanceDepth,
      parentChildResolution: rec.parentChildResolution,
      childCanOverrideParentDeny: rec.childCanOverrideParentDeny,
      childCanAddAllow: rec.childCanAddAllow,
    },
    resolutionStrategy: rec.resolutionStrategy,
    isolationLevel: rec.isolationLevel,
  };
}

// ─── Helper: Load policies for a namespace ────────────────────────────

/** Maximum policies to load per namespace to prevent OOM on 500MB Termux */
const MAX_POLICIES_PER_NAMESPACE = 200;

/**
 * Load all PolicyDocuments associated with a namespace.
 * BUG #3 FIX: Added take limits to all queries to prevent OOM.
 * BUG #11 FIX: Uses SQL-side filtering where possible instead of
 * loading all policies and filtering in JS.
 */
async function loadNamespacePolicies(namespaceId: string, tenantId: string): Promise<PolicyDocument[]> {
  const policies: PolicyDocument[] = [];
  const seenPolicyIds = new Set<string>();

  // 1. Load policies via DeclPolicy labels containing namespace reference
  // BUG #11 FIX: Use contains filter at SQL level instead of full table scan
  const labeledPolicies = await db.declPolicy.findMany({
    where: {
      isActive: true,
      OR: [
        { labels: { contains: `"namespace":"${namespaceId}"` } },
        { labels: { contains: `"zenic.dev/namespace":"${namespaceId}"` } },
      ],
    },
    take: MAX_POLICIES_PER_NAMESPACE,
  });

  for (const p of labeledPolicies) {
    if (seenPolicyIds.has(p.policyId)) continue;
    try {
      const labels = JSON.parse(p.labels) as Record<string, string>;
      seenPolicyIds.add(p.policyId);
      policies.push({
        apiVersion: p.apiVersion,
        kind: "PolicyDocument" as const,
        metadata: {
          id: p.policyId,
          name: p.name,
          version: p.version,
          description: p.description,
          compliance: JSON.parse(p.compliance),
          labels,
          author: p.author ?? undefined,
          createdAt: p.createdAt.toISOString(),
          updatedAt: p.updatedAt.toISOString(),
        },
        statements: JSON.parse(p.statements),
        tests: JSON.parse(p.tests),
      });
    } catch {
      // Skip policies with malformed labels
    }
  }

  // 2. Load policies via PolicySet.namespace field
  const policySets = await db.policySet.findMany({
    where: {
      namespace: namespaceId,
      isActive: true,
    },
  });

  for (const set of policySets) {
    try {
      const entries = JSON.parse(set.policies) as Array<{ policyId: string; version?: string; required?: boolean }>;
      // BUG #3 FIX: Batch-load all referenced policies in ONE query instead of N+1
      const policyIds = entries
        .map((e) => e.policyId)
        .filter((id) => !seenPolicyIds.has(id));

      if (policyIds.length > 0) {
        const batchPolicies = await db.declPolicy.findMany({
          where: {
            policyId: { in: policyIds },
            isActive: true,
          },
          take: MAX_POLICIES_PER_NAMESPACE - policies.length,
        });

        for (const policy of batchPolicies) {
          if (seenPolicyIds.has(policy.policyId)) continue;
          seenPolicyIds.add(policy.policyId);
          policies.push({
            apiVersion: policy.apiVersion,
            kind: "PolicyDocument" as const,
            metadata: {
              id: policy.policyId,
              name: policy.name,
              version: policy.version,
              description: policy.description,
              compliance: JSON.parse(policy.compliance),
              labels: JSON.parse(policy.labels),
              author: policy.author ?? undefined,
              createdAt: policy.createdAt.toISOString(),
              updatedAt: policy.updatedAt.toISOString(),
            },
            statements: JSON.parse(policy.statements),
            tests: JSON.parse(policy.tests),
          });
        }
      }
    } catch {
      // Skip sets with malformed policy entries
    }
  }

  // 3. Load tenant-scoped policies without explicit namespace (only if room remains)
  // BUG #3 FIX: Use SQL filtering + take limit
  if (policies.length < MAX_POLICIES_PER_NAMESPACE) {
    const tenantPolicies = await db.declPolicy.findMany({
      where: {
        isActive: true,
        labels: { contains: `"tenantId":"${tenantId}"` },
      },
      take: MAX_POLICIES_PER_NAMESPACE - policies.length,
    });

    for (const p of tenantPolicies) {
      if (seenPolicyIds.has(p.policyId)) continue;
      try {
        const labels = JSON.parse(p.labels) as Record<string, string>;
        // Only include policies without explicit namespace
        if (labels.namespace || labels["zenic.dev/namespace"]) continue;
        seenPolicyIds.add(p.policyId);
        policies.push({
          apiVersion: p.apiVersion,
          kind: "PolicyDocument" as const,
          metadata: {
            id: p.policyId,
            name: p.name,
            version: p.version,
            description: p.description,
            compliance: JSON.parse(p.compliance),
            labels,
            author: p.author ?? undefined,
            createdAt: p.createdAt.toISOString(),
            updatedAt: p.updatedAt.toISOString(),
          },
          statements: JSON.parse(p.statements),
          tests: JSON.parse(p.tests),
        });
      } catch {
        // Skip policies with malformed labels
      }
    }
  }

  return policies;
}

// ─── Strategy: Restrictiveness Ordering ───────────────────────────────

const RESTRICTIVENESS_ORDER: Record<PolicyEffectV2, number> = {
  deny: 0,
  conditional: 1,
  allow: 2,
};

function isMoreRestrictive(a: PolicyEffectV2, b: PolicyEffectV2): boolean {
  return (RESTRICTIVENESS_ORDER[a] ?? 3) < (RESTRICTIVENESS_ORDER[b] ?? 3);
}

// ─── Strategy: Resolve with parent-child rules ────────────────────────

/**
 * Apply parent-child hierarchy constraints on evaluation results.
 * Checks childCanOverrideParentDeny and childCanAddAllow constraints.
 */
function applyParentChildConstraints(
  childResult: PolicyEvaluationResult,
  parentResult: PolicyEvaluationResult,
  hierarchy: NamespaceHierarchy,
): PolicyEvaluationResult {
  // If child says ALLOW but parent says DENY, and child cannot override
  if (
    childResult.effect === "allow" &&
    parentResult.effect === "deny" &&
    !hierarchy.childCanOverrideParentDeny
  ) {
    return {
      ...parentResult,
      reason: `Parent DENY overrides child ALLOW (childCanOverrideParentDeny=false): ${parentResult.reason}`,
    };
  }

  // If child adds ALLOW but is not allowed to
  if (
    childResult.effect === "allow" &&
    parentResult.effect !== "allow" &&
    !hierarchy.childCanAddAllow
  ) {
    return {
      ...parentResult,
      reason: `Child cannot add ALLOW rules (childCanAddAllow=false): parent effect ${parentResult.effect} preserved`,
    };
  }

  return childResult;
}

/**
 * Resolve conflicts between parent and child namespace results
 * using the parentChildResolution strategy.
 */
function resolveParentChildConflict(
  childResult: PolicyEvaluationResult,
  parentResult: PolicyEvaluationResult,
  hierarchy: NamespaceHierarchy,
): PolicyEvaluationResult {
  const strategy = hierarchy.parentChildResolution;

  switch (strategy) {
    case ConflictStrategy.DENY_WINS:
      if (childResult.effect === "deny" || parentResult.effect === "deny") {
        const denyResult = childResult.effect === "deny" ? childResult : parentResult;
        return {
          ...denyResult,
          reason: `DENY_WINS resolution: ${denyResult.reason}`,
        };
      }
      // Neither is deny — keep child result (closer to request)
      return childResult;

    case ConflictStrategy.PRIORITY_WINS: {
      // Compare by matched statement priority
      const childPrio = childResult.matchedStatements[0]?.priority ?? -1;
      const parentPrio = parentResult.matchedStatements[0]?.priority ?? -1;
      if (parentPrio > childPrio) {
        return {
          ...parentResult,
          reason: `PRIORITY_WINS resolution (parent priority ${parentPrio} > child ${childPrio}): ${parentResult.reason}`,
        };
      }
      return {
        ...childResult,
        reason: `PRIORITY_WINS resolution (child priority ${childPrio} >= parent ${parentPrio}): ${childResult.reason}`,
      };
    }

    case ConflictStrategy.MERGE_CONDITIONS: {
      // Both conditions must be satisfied — the more restrictive wins
      if (isMoreRestrictive(parentResult.effect, childResult.effect)) {
        return {
          ...childResult,
          reason: `MERGE_CONDITIONS resolution (child more restrictive): ${childResult.reason}`,
        };
      }
      return {
        ...parentResult,
        reason: `MERGE_CONDITIONS resolution (parent more restrictive): ${parentResult.reason}`,
      };
    }

    case ConflictStrategy.FIRST_MATCH:
      // Child is evaluated first, so child wins
      return childResult;

    case ConflictStrategy.MANUAL:
      // Return child but flag that manual resolution is needed
      return {
        ...childResult,
        reason: `MANUAL resolution required — child result preserved: ${childResult.reason}`,
      };

    default:
      return applyParentChildConstraints(childResult, parentResult, hierarchy);
  }
}

// ─── Core Evaluation Strategies ───────────────────────────────────────

/**
 * LOCAL_FIRST strategy: Evaluate local namespace first.
 * If no definitive result (deny-by-default), walk up to parent.
 */
async function evaluateLocalFirst(
  request: PolicyEvaluationRequest,
  namespaceRec: NamespaceDbRecord,
  evaluator: PolicyEvaluator,
  trace: NamespaceEvaluationTrace[],
  depth: number,
