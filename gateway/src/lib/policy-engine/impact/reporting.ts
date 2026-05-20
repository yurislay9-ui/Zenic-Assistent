    (pb) => pb.complianceScoreChange !== 0,
  );
  riskScore += playbooksWithComplianceChange.length * 10;

  // Cap at 100
  riskScore = Math.min(riskScore, 100);

  // Risk level
  const riskLevel: SimulationRiskLevel =
    riskScore <= 20 ? SimulationRiskLevelValues.LOW :
    riskScore <= 50 ? SimulationRiskLevelValues.MEDIUM :
    riskScore <= 80 ? SimulationRiskLevelValues.HIGH :
    SimulationRiskLevelValues.CRITICAL;

  // Total affected resources
  const resourceIds = new Set<string>();
  for (const d of directDeps) resourceIds.add(`${d.type}:${d.id}`);
  for (const d of indirectDeps) resourceIds.add(`${d.type}:${d.id}`);
  for (const s of affectedSets) resourceIds.add(`policy_set:${s.setId}`);
  for (const p of affectedPlaybooks) resourceIds.add(`playbook:${p.playbookId}`);
  for (const t of affectedTools) resourceIds.add(`tool:${t.toolId}`);

  // Estimated users affected (based on roles linked to tools and playbooks)
  const estimatedUsers = estimateAffectedUsers(affectedTools, affectedPlaybooks);

  // Impact categories
  const categories = buildImpactCategories(
    affectedSets,
    affectedPlaybooks,
    affectedTools,
    downstreamChanges,
    complianceStandardsImpacted,
    estimatedUsers,
  );

  return {
    totalAffectedResources: resourceIds.size,
    totalAffectedUsers: estimatedUsers,
    riskScore,
    riskLevel,
    estimatedRecoveryMinutes: riskScore * 2,
    categories,
  };
}

/**
 * Estimate the number of affected users based on tool risk levels and playbook activations.
 */
function estimateAffectedUsers(
  tools: AffectedToolRef[],
  playbooks: AffectedPlaybookRef[],
): number {
  let users = 0;

  // Estimate users per tool by risk level
  for (const tool of tools) {
    switch (tool.riskLevel) {
      case "critical": users += 50; break;
      case "high": users += 30; break;
      case "medium": users += 15; break;
      default: users += 5; break;
    }
  }

  // Estimate users per playbook activation (industry-based)
  for (const pb of playbooks) {
    users += 20; // baseline per playbook
  }

  return users;
}

/**
 * Build impact categories for the blast radius.
 */
function buildImpactCategories(
  sets: AffectedSetRef[],
  playbooks: AffectedPlaybookRef[],
  tools: AffectedToolRef[],
  changes: DownstreamChange[],
  complianceStandardsImpacted: number,
  estimatedUsers: number,
): ImpactCategory[] {
  const categories: ImpactCategory[] = [];

  // Policy Sets
  if (sets.length > 0) {
    const maxPriority = Math.max(...sets.map((s) => s.priority), 0);
    categories.push({
      name: "Policy Sets",
      affectedCount: sets.length,
      severity: maxPriority >= 100 ? ConflictSeverityValues.CRITICAL :
                maxPriority >= 50 ? ConflictSeverityValues.HIGH :
                ConflictSeverityValues.MEDIUM,
      description: `${sets.length} policy set(s) reference the target policy and may need re-composition`,
    });
  }

  // Playbooks
  if (playbooks.length > 0) {
    categories.push({
      name: "Playbooks",
      affectedCount: playbooks.length,
      severity: playbooks.length >= 5 ? ConflictSeverityValues.HIGH :
                playbooks.length >= 2 ? ConflictSeverityValues.MEDIUM :
                ConflictSeverityValues.LOW,
      description: `${playbooks.length} playbook(s) activate this policy across industries`,
    });
  }

  // Tools
  const toolsWithVerdictChange = changes.length;
  if (toolsWithVerdictChange > 0 || tools.length > 0) {
    const allowToDeny = changes.filter(
      (c) => c.currentEffect === "allow" && c.predictedEffect === "deny",
    ).length;
    categories.push({
      name: "Tools",
      affectedCount: toolsWithVerdictChange || tools.length,
      severity: allowToDeny > 0 ? ConflictSeverityValues.CRITICAL :
                toolsWithVerdictChange > 0 ? ConflictSeverityValues.HIGH :
                ConflictSeverityValues.MEDIUM,
      description: `${toolsWithVerdictChange} tool(s) with verdict changes, ${tools.length} total tools protected by this policy`,
    });
  }

  // Compliance
  if (complianceStandardsImpacted > 0) {
    categories.push({
      name: "Compliance",
      affectedCount: complianceStandardsImpacted,
      severity: complianceStandardsImpacted >= 3 ? ConflictSeverityValues.CRITICAL :
                complianceStandardsImpacted >= 2 ? ConflictSeverityValues.HIGH :
                ConflictSeverityValues.MEDIUM,
      description: `${complianceStandardsImpacted} compliance standard(s) may be impacted by this policy change`,
    });
  }

  // Users
  if (estimatedUsers > 0) {
    categories.push({
      name: "Users",
      affectedCount: estimatedUsers,
      severity: estimatedUsers >= 100 ? ConflictSeverityValues.CRITICAL :
                estimatedUsers >= 50 ? ConflictSeverityValues.HIGH :
                estimatedUsers >= 10 ? ConflictSeverityValues.MEDIUM :
                ConflictSeverityValues.LOW,
      description: `Estimated ${estimatedUsers} user(s) affected by access changes`,
    });
  }

  return categories;
}

/**
 * Count compliance standards impacted by this policy.
 */
async function countComplianceStandards(policyId: string): Promise<number> {
  try {
    const policy = await db.declPolicy.findUnique({
      where: { policyId },
    });

    if (!policy) return 0;

    const compliance = JSON.parse(policy.compliance) as Array<{ standard: string }>;
    const standards = new Set(compliance.map((c) => c.standard));

    // Also check if affected playbooks reference additional standards
    const referencingPlaybooks = await findReferencingPlaybooks(policyId);
    for (const pb of referencingPlaybooks) {
      const pbCompliance = JSON.parse(
        (await db.playbook.findUnique({ where: { playbookId: pb.playbookId } }))
          ?.compliance ?? "[]",
      ) as string[];
      for (const std of pbCompliance) {
        standards.add(std);
      }
    }

    return standards.size;
  } catch {
    return 0;
  }
}

// ─── Core: Transitive Closure (DEEP depth) ─────────────────────────────

/**
 * Build full transitive closure of dependencies.
 * Follows indirect references until no new nodes are discovered.
 */
async function buildTransitiveClosure(
  initialIndirectNodes: DependencyNode[],
  visited: Set<string>,
  maxDepth: number,
  currentDepth: number,
): Promise<DependencyNode[]> {
  if (currentDepth >= maxDepth && maxDepth !== -1) return [];
  if (initialIndirectNodes.length === 0) return [];

  const allNewNodes: DependencyNode[] = [];

  for (const node of initialIndirectNodes) {
    if (visited.has(node.id)) continue;
    visited.add(node.id);

    if (node.type === "policy") {
      // Find what references this policy (policy sets, playbooks, tools)
      const policyId = node.id;

      // PolicySets referencing this policy
      const policySets = await findReferencingPolicySets(policyId);
      for (const ps of policySets) {
        const childNode: DependencyNode = {
          id: ps.setId,
          type: "policy_set",
          name: ps.name,
          dependencyType: DependencyTypeValues.COMPOSED_BY,
          hardDependency: ps.entry.required,
          children: [],
        };
        node.children.push(childNode);
        allNewNodes.push(childNode);
      }

      // Playbooks referencing this policy
      const playbooks = await findReferencingPlaybooks(policyId);
      for (const pb of playbooks) {
        const childNode: DependencyNode = {
          id: pb.playbookId,
          type: "playbook",
          name: pb.name,
          dependencyType: DependencyTypeValues.ACTIVATED_BY,
          hardDependency: false,
          children: [],
        };
        node.children.push(childNode);
        allNewNodes.push(childNode);
      }

      // Recurse into children
      const deeper = await buildTransitiveClosure(
        node.children,
        visited,
        maxDepth,
        currentDepth + 1,
      );
      allNewNodes.push(...deeper);
    }
  }

  return allNewNodes;
}

// ─── Main: analyzeImpact ───────────────────────────────────────────────

/**
 * Analyze the impact of changing a policy.
 *
 * Steps:
 *   1. Load the target policy from DB
 *   2. Find direct dependencies (policy sets, playbooks, tools, approvals)
 *   3. Find indirect dependencies (based on analysis depth strategy)
 *   4. Predict downstream evaluation changes
 *   5. Calculate blast radius
 *   6. Persist to DB
 *   7. Return ImpactAnalysisResult
 */
export async function analyzeImpact(
  request: ImpactAnalysisRequest,
): Promise<ImpactAnalysisResult> {
  const { policyId, proposedVersion, proposedDocument, depth, requestedBy } = request;

  // 1. Load target policy
  const currentDocument = await loadPolicyFromDb(policyId);
  if (!currentDocument) {
    throw new Error(`[ImpactAnalysis] Policy "${policyId}" not found`);
  }

  const strategy = DEPTH_STRATEGIES[depth];
  const visitor = new ImpactCollectorVisitor();

  // ── 2. Find direct dependencies ────────────────────────────────────

  // 2a. PolicySets that reference this policy
  const referencingSets = await findReferencingPolicySets(policyId);
  for (const ps of referencingSets) {
    const node: DependencyNode = {
      id: ps.setId,
      type: "policy_set",
      name: ps.name,
      dependencyType: DependencyTypeValues.REFERENCES,
      hardDependency: ps.entry.required,
      children: [],
    };

    const setRef: AffectedSetRef = {
      setId: ps.setId,
      name: ps.name,
      priority: ps.entry.priority,
      needsRecomposition: true,
    };
    node.data = setRef;

    visitor.visitDirect(node);
  }

  // 2b. Playbooks that activate this policy
  const referencingPlaybooks = await findReferencingPlaybooks(policyId);
  for (const pb of referencingPlaybooks) {
    const policyRefs = JSON.parse(pb.policies) as Array<{ policyId: string; role?: string }>;
    const thisRef = policyRefs.find((r) => r.policyId === policyId);

    const node: DependencyNode = {
      id: pb.playbookId,
      type: "playbook",
      name: pb.name,
      dependencyType: DependencyTypeValues.ACTIVATED_BY,
      hardDependency: false,
      children: [],
    };

    const pbRef: AffectedPlaybookRef = {
      playbookId: pb.playbookId,
      name: pb.name,
      industry: pb.industry,
      role: thisRef?.role ?? "unknown",
      complianceScoreChange: 0, // will be updated if strategy includes compliance
    };
    node.data = pbRef;

    visitor.visitDirect(node);
  }

  // 2c. Tools protected by this policy
  const protectedTools = await findProtectedTools(policyId);
  const toolRefsMap = new Map<string, AffectedToolRef>();

  for (const tool of protectedTools) {
    const currentVerdict = (tool.accessPolicyEffect as PolicyEffectV2) || "deny";

    const node: DependencyNode = {
      id: tool.toolId,
      type: "tool",
      name: tool.toolName,
      dependencyType: DependencyTypeValues.PROTECTED_BY,
      hardDependency: true,
      children: [],
    };
