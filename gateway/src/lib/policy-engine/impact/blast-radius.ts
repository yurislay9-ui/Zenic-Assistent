async function findReferencingApprovals(policyId: string): Promise<Array<{
  approvalId: string;
  title: string;
  status: string;
  priority: string;
  requestedBy: string;
}>> {
  const results: Array<{
    approvalId: string;
    title: string;
    status: string;
    priority: string;
    requestedBy: string;
  }> = [];

  try {
    const approvals = await db.policyApproval.findMany({
      where: { targetPolicyId: policyId },
    });

    for (const a of approvals) {
      results.push({
        approvalId: a.approvalId,
        title: a.title,
        status: a.status,
        priority: a.priority,
        requestedBy: a.requestedBy,
      });
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find referencing approvals:", error);
  }

  return results;
}

// ─── Core: Indirect Dependency Finder ───────────────────────────────────

/**
 * Find policies composed with the target in the same PolicySets.
 */
async function findComposedPolicies(
  policySetIds: string[],
  excludePolicyId: string,
): Promise<DependencyNode[]> {
  const nodes: DependencyNode[] = [];

  try {
    for (const setId of policySetIds) {
      const ps = await db.policySet.findUnique({
        where: { setId },
      });

      if (!ps) continue;

      const entries: PolicySetEntry[] = JSON.parse(ps.policies);
      for (const entry of entries) {
        if (entry.policyId === excludePolicyId) continue;

        // Check if the referenced policy exists
        const exists = await db.declPolicy.findUnique({
          where: { policyId: entry.policyId },
        });

        if (exists) {
          nodes.push({
            id: entry.policyId,
            type: "policy",
            name: exists.name,
            dependencyType: DependencyTypeValues.COMPOSED_BY,
            hardDependency: entry.required,
            children: [],
            data: {
              policyId: entry.policyId,
              version: entry.version,
              priority: entry.priority,
              required: entry.required,
              setName: ps.name,
            },
          });
        }
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find composed policies:", error);
  }

  return nodes;
}

/**
 * Find other policies referenced by affected playbooks.
 */
async function findPlaybookSiblingPolicies(
  playbookIds: string[],
  excludePolicyId: string,
): Promise<DependencyNode[]> {
  const nodes: DependencyNode[] = [];
  const seen = new Set<string>();

  try {
    for (const playbookId of playbookIds) {
      const pb = await db.playbook.findUnique({
        where: { playbookId },
      });

      if (!pb) continue;

      const policyRefs = JSON.parse(pb.policies) as Array<{ policyId: string; role?: string }>;
      for (const ref of policyRefs) {
        if (ref.policyId === excludePolicyId) continue;
        if (seen.has(ref.policyId)) continue;
        seen.add(ref.policyId);

        const exists = await db.declPolicy.findUnique({
          where: { policyId: ref.policyId },
        });

        if (exists) {
          nodes.push({
            id: ref.policyId,
            type: "policy",
            name: exists.name,
            dependencyType: DependencyTypeValues.ACTIVATED_BY,
            hardDependency: false,
            children: [],
            data: {
              policyId: ref.policyId,
              role: ref.role ?? "unknown",
              playbookName: pb.name,
            },
          });
        }
      }
    }
  } catch (error) {
    console.error("[ImpactAnalysis] Failed to find playbook sibling policies:", error);
  }

  return nodes;
}

// ─── Core: Downstream Change Prediction ────────────────────────────────

/**
 * Predict downstream evaluation changes for affected tools.
 * Compares current verdict vs proposed verdict.
 */
async function predictDownstreamChanges(
  currentDocument: PolicyDocument,
  proposedDocument: PolicyDocument | undefined,
  affectedTools: AffectedToolRef[],
  depth: ImpactAnalysisDepth,
): Promise<DownstreamChange[]> {
  const changes: DownstreamChange[] = [];

  if (!proposedDocument) {
    // Without a proposed document, we can only estimate based on policy removal
    for (const tool of affectedTools) {
      changes.push({
        request: `tool:${tool.toolId}`,
        currentEffect: tool.currentVerdict,
        predictedEffect: "deny" as PolicyEffectV2, // removal defaults to deny
        confidence: 0.6,
        reason: "Policy change may remove current access — deny-by-default fallback",
      });
    }
    return changes;
  }

  // For each affected tool, compare current vs proposed verdict
  for (const tool of affectedTools) {
    const currentVerdict = tool.currentVerdict;

    // Simulate proposed document evaluation for this tool
    const proposedVerdict = simulateVerdict(proposedDocument, tool.name, "execute");

    if (currentVerdict !== proposedVerdict) {
      changes.push({
        request: `tool:${tool.toolId}`,
        currentEffect: currentVerdict,
        predictedEffect: proposedVerdict,
        confidence: depth === ImpactAnalysisDepthValues.DEEP ? 0.9 :
                    depth === ImpactAnalysisDepthValues.STANDARD ? 0.75 : 0.6,
        reason: buildChangeReason(currentVerdict, proposedVerdict, tool.name),
      });
    }
  }

  return changes;
}

/**
 * Simple verdict simulation based on document statement matching.
 */
function simulateVerdict(
  document: PolicyDocument,
  resourceName: string,
  actionName: string,
): PolicyEffectV2 {
  const matchedStatements = document.statements.filter((stmt) => {
    const resourceMatch = stmt.resource === "*" ||
      stmt.resource === resourceName ||
      (stmt.resource.endsWith("/*") && resourceName.startsWith(stmt.resource.slice(0, -2)));

    const actionMatch = stmt.action === "*" ||
      stmt.action === actionName;

    return resourceMatch && actionMatch;
  });

  if (matchedStatements.length === 0) {
    return "deny"; // deny-by-default
  }

  // Sort by priority (highest first), deny wins on tie
  matchedStatements.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    const effectOrder: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };
    return (effectOrder[a.effect] ?? 3) - (effectOrder[b.effect] ?? 3);
  });

  return matchedStatements[0]!.effect as PolicyEffectV2;
}

/**
 * Build a human-readable reason for a verdict change.
 */
function buildChangeReason(
  from: PolicyEffectV2,
  to: PolicyEffectV2,
  toolName: string,
): string {
  if (from === "allow" && to === "deny") {
    return `Tool "${toolName}" will be BLOCKED — access changes from ALLOW to DENY`;
  }
  if (from === "deny" && to === "allow") {
    return `Tool "${toolName}" will be OPENED — access changes from DENY to ALLOW`;
  }
  if (from === "allow" && to === "conditional") {
    return `Tool "${toolName}" will require CONDITIONAL approval instead of ALLOW`;
  }
  if (from === "deny" && to === "conditional") {
    return `Tool "${toolName}" will become CONDITIONAL instead of DENY`;
  }
  if (from === "conditional" && to === "deny") {
    return `Tool "${toolName}" will be BLOCKED — conditional access removed, now DENY`;
  }
  if (from === "conditional" && to === "allow") {
    return `Tool "${toolName}" will be fully ALLOWED — conditional restriction removed`;
  }
  return `Tool "${toolName}" verdict changes from ${from} to ${to}`;
}

// ─── Core: Blast Radius Calculation ────────────────────────────────────

/**
 * Calculate blast radius from analysis components.
 *
 * Risk score formula:
 *   - 10 points per direct dependency
 *   - 5 points per indirect dependency
 *   - 20 points per tool that changes from ALLOW → DENY
 *   - 15 points per tool that changes from DENY → ALLOW
 *   - 10 points per playbook with compliance score change
 *   - Cap at 100
 *
 * Risk levels:
 *   - 0-20: LOW
 *   - 21-50: MEDIUM
 *   - 51-80: HIGH
 *   - 81-100: CRITICAL
 *
 * Recovery time: riskScore * 2 minutes
 */
function calculateBlastRadius(
  directDeps: DependencyRef[],
  indirectDeps: DependencyRef[],
  affectedSets: AffectedSetRef[],
  affectedPlaybooks: AffectedPlaybookRef[],
  affectedTools: AffectedToolRef[],
  downstreamChanges: DownstreamChange[],
  complianceStandardsImpacted: number,
): BlastRadius {
  // Risk score components
  let riskScore = 0;

  riskScore += directDeps.length * 10;
  riskScore += indirectDeps.length * 5;

  for (const change of downstreamChanges) {
    if (change.currentEffect === "allow" && change.predictedEffect === "deny") {
      riskScore += 20;
    } else if (change.currentEffect === "deny" && change.predictedEffect === "allow") {
      riskScore += 15;
    }
  }

  // Playbooks with compliance score change
  const playbooksWithComplianceChange = affectedPlaybooks.filter(
