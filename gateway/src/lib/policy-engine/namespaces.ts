// ─── Zenic-Agents v3 — Policy Namespace Engine ────────────────────────
// Multi-tenant policy scoping with hierarchical inheritance.
// Phase 4: Declarative Versioned Policy Engine — Namespace Module
//
// Design Patterns:
//   - Chain of Responsibility: namespace hierarchy evaluation
//   - Strategy: resolution strategies (local_first, priority_based, deny_wins, most_restrictive)
//   - Composite: namespace tree with parent-child relationships

import { db } from "@/lib/db";
import type {
  PolicyDocument,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
  PolicyEffectV2,
  PolicyStatement,
} from "./types";
import type {
  PolicyNamespace,
  NamespaceHierarchy,
  NamespaceResolutionStrategy,
  NamespaceIsolationLevel,
  NamespaceResolutionResult,
  ConflictResolutionStrategy,
} from "./types";
import {
  NamespaceResolutionStrategy as ResolutionStrategy,
  ConflictResolutionStrategy as ConflictStrategy,
  NAMESPACE_API_VERSION as NS_API_VERSION,
  NAMESPACE_KIND as NS_KIND,
} from "./types";
import { PolicyEvaluator, getPolicyEvaluator } from "./evaluator";

// ─── Namespace Engine Error Types ─────────────────────────────────────

/** Error thrown when a namespace operation fails validation */
export class NamespaceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "NamespaceError";
  }
}

// ─── DB Record Mapper ─────────────────────────────────────────────────

/** Internal representation of a namespace DB row mapped to typed fields */
interface NamespaceDbRecord {
  id: string;
  namespaceId: string;
  name: string;
  description: string;
  tenantId: string;
  parentNamespaceId: string | null;
  path: string;
  labels: Record<string, string>;
  inheritFromParent: boolean;
  maxInheritanceDepth: number;
  parentChildResolution: ConflictResolutionStrategy;
  childCanOverrideParentDeny: boolean;
  childCanAddAllow: boolean;
  resolutionStrategy: NamespaceResolutionStrategy;
  isolationLevel: NamespaceIsolationLevel;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

/** Updates that can be applied to a namespace */
export interface NamespaceUpdateRequest {
  name?: string;
  description?: string;
  labels?: Record<string, string>;
  inheritFromParent?: boolean;
  maxInheritanceDepth?: number;
  parentChildResolution?: ConflictResolutionStrategy;
  childCanOverrideParentDeny?: boolean;
  childCanAddAllow?: boolean;
  resolutionStrategy?: NamespaceResolutionStrategy;
  isolationLevel?: NamespaceIsolationLevel;
}

/** A single step in the namespace evaluation trace */
interface NamespaceEvaluationTrace {
  namespaceId: string;
  namespacePath: string;
  depth: number;
  policiesEvaluated: number;
  result: PolicyEvaluationResult | null;
  inherited: boolean;
}

// ─── Helper: Map DB Row to NamespaceDbRecord ──────────────────────────

function mapDbToRecord(row: {
  id: string;
  namespaceId: string;
  name: string;
  description: string;
  tenantId: string;
  parentNamespaceId: string | null;
  path: string;
  labels: string;
  inheritFromParent: boolean;
  maxInheritanceDepth: number;
  parentChildResolution: string;
  childCanOverrideParentDeny: boolean;
  childCanAddAllow: boolean;
  resolutionStrategy: string;
  isolationLevel: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}): NamespaceDbRecord {
  return {
    id: row.id,
    namespaceId: row.namespaceId,
    name: row.name,
    description: row.description,
    tenantId: row.tenantId,
    parentNamespaceId: row.parentNamespaceId,
    path: row.path,
    labels: JSON.parse(row.labels),
    inheritFromParent: row.inheritFromParent,
    maxInheritanceDepth: row.maxInheritanceDepth,
    parentChildResolution: row.parentChildResolution as ConflictResolutionStrategy,
    childCanOverrideParentDeny: row.childCanOverrideParentDeny,
    childCanAddAllow: row.childCanAddAllow,
    resolutionStrategy: row.resolutionStrategy as NamespaceResolutionStrategy,
    isolationLevel: row.isolationLevel as NamespaceIsolationLevel,
    isActive: row.isActive,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}

// ─── Helper: Map DB Record to PolicyNamespace ─────────────────────────

function mapRecordToPolicyNamespace(rec: NamespaceDbRecord): PolicyNamespace {
  return {
    apiVersion: NS_API_VERSION,
    kind: NS_KIND,
    metadata: {
      id: rec.namespaceId,
      name: rec.name,
      description: rec.description,
      tenantId: rec.tenantId,
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
